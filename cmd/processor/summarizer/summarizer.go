package summarizer

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"tech-letter/config"
	"time"

	"google.golang.org/genai"
)

type SummarizeResult struct {
	Summary    string   `json:"summary"`
	Categories []string `json:"categories"`
	Tags       []string `json:"tags"`
	Error      *string  `json:"error,omitempty"`
}

type LLMRequestLog struct {
	Prompt       string     `json:"prompt"`
	Response     string     `json:"response"`
	LatencyMs    int64      `json:"latency_ms"`
	TokenUsage   TokenUsage `json:"token_usage"`
	ModelName    string     `json:"model_name"`
	ModelVersion string     `json:"model_version"`
	GeneratedAt  time.Time  `json:"generated_at"`
}

type TokenUsage struct {
	InputTokens  int64 `json:"input_tokens"`
	OutputTokens int64 `json:"output_tokens"`
	TotalTokens  int64 `json:"total_tokens"`
}

const SYSTEM_INSTRUCTION = `
You are a content summarization assistant for technical blog posts.
Your task is to analyze the provided text and produce a structured summary.
The response MUST be a valid JSON object with five keys:

1. summary: A concise summary of the blog post, no more than 200 characters. Always be polite.
   (Written in Korean)
2. error: An optional string field. If the content contains a security check
   (e.g., "I'm not a bot," "Are you human?") that prevents summarization,
   set this field to a descriptive error message. Otherwise, set it to 'null'.
4. categories: A list of 1–3 categories that best describe the blog post.
   You MUST choose only from the following predefined category list (English terms):
   ["Backend", "Frontend", "Mobile", "AI", "Data Engineering", "DevOps", "Security",
    "Cloud", "Database", "Programming Languages", "Infrastructure", "Other"].
5. tags: A list of 3–7 keywords that represent the **specific technologies, libraries, frameworks,
   tools, languages, or protocols** explicitly mentioned in the text.
   - Tags MUST be concrete and reusable terms (e.g., "Hadoop", "React", "Kubernetes").
   - Do NOT include generic concepts (e.g., "AI development", "storage cost") or long phrases.
   - Remove duplicates.

Additional constraints:
- Only 'summary' should be written in Korean. All other fields (categories, tags) remain in English.
- You MUST NOT wrap the JSON output in a markdown code block (e.g., ` + "```json ... ```" + `).
- The response should contain ONLY the raw JSON string.
- If summarization fails, set the 'error' field to an appropriate message (e.g., "Content contains a security check preventing summarization.")
  and provide an empty string for 'summary', and empty arrays for 'categories' and 'tags'.
`

func SummarizeText(text string) (*SummarizeResult, *LLMRequestLog, error) {
	startTime := time.Now()

	apiKey := os.Getenv("GEMINI_API_KEY")
	if apiKey == "" {
		return nil, nil, fmt.Errorf("GEMINI_API_KEY environment variable is not set")
	}
	llmCfg := config.GetConfig().Processor.LLM
	if llmCfg.Provider != "google" {
		return nil, nil, fmt.Errorf("unsupported LLM provider: %s", llmCfg.Provider)
	}
	modelName := llmCfg.ModelName

	ctx := context.Background()
	client, err := genai.NewClient(ctx, &genai.ClientConfig{
		APIKey: apiKey,
	})
	if err != nil {
		return nil, nil, err
	}

	result, err := client.Models.GenerateContent(
		ctx,
		modelName,
		genai.Text(text),
		&genai.GenerateContentConfig{
			SystemInstruction: &genai.Content{Parts: []*genai.Part{{Text: SYSTEM_INSTRUCTION}}},
		},
	)
	if err != nil {
		return nil, nil, err
	}

	var summary SummarizeResult
	if err := json.Unmarshal([]byte(result.Text()), &summary); err != nil {
		return nil, nil, err
	}

	if summary.Error != nil {
		return &summary, nil, fmt.Errorf("ai judged that this content is not summarizable: %s", *summary.Error)
	}

	if result == nil || result.UsageMetadata == nil {
		return &summary, nil, fmt.Errorf("result or usage metadata is nil")
	}

	llmLog := &LLMRequestLog{
		Prompt:    fmt.Sprintf("%s\n\n%s", SYSTEM_INSTRUCTION, text),
		Response:  result.Text(),
		LatencyMs: time.Since(startTime).Milliseconds(),
		TokenUsage: TokenUsage{
			InputTokens:  int64(result.UsageMetadata.PromptTokenCount),
			OutputTokens: int64(result.UsageMetadata.CandidatesTokenCount),
			TotalTokens:  int64(result.UsageMetadata.TotalTokenCount),
		},
		ModelName:    modelName,
		ModelVersion: result.ModelVersion,
		GeneratedAt:  time.Now(),
	}

	return &summary, llmLog, nil
}
