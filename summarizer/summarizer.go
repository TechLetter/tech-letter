package summarizer

import (
	"context"
	"encoding/json"
	"tech-letter/config"

	"google.golang.org/genai"
)

type SummarizeResult struct {
	SummaryShort string   `json:"summary_short"`
	SummaryLong  string   `json:"summary_long"`
	Categories   []string `json:"categories"`
	Tags         []string `json:"tags"`
	IsFailure    bool     `json:"is_failure"`
}

const SYSTEM_INSTRUCTION = `
You are a content summarization assistant for technical blog posts. 
Your task is to analyze the provided text and produce a structured summary. 
The response MUST be a valid JSON object with five keys:

1. summary_short: A concise summary of the blog post, no more than 200 characters. 
   (Written in Korean)
2. summary_long: A detailed summary of the blog post, no more than 1000 characters. 
   (Written in Korean)
3. is_failure: A boolean value. Set to true if the content contains a security check 
   (e.g., "I'm not a bot," "Are you human?") that prevents summarization. Otherwise, set to false.
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
- Only summary_short and summary_long should be written in Korean. All other fields (categories, tags) remain in English.
- You MUST NOT wrap the JSON output in a markdown code block (e.g., ` + "```json ... ```" + `). 
- The response should contain ONLY the raw JSON string.
- If summarization fails, set is_failure to true and provide an empty string for summary_short, 
  summary_long, categories, and tags.
`

func SummarizeText(text string) (*SummarizeResult, error) {

	ctx := context.Background()
	client, err := genai.NewClient(ctx, &genai.ClientConfig{
		APIKey: config.GetConfig().GeminiApiKey,
	})
	if err != nil {
		return nil, err
	}

	result, err := client.Models.GenerateContent(
		ctx,
		config.GetConfig().GeminiModel,
		genai.Text(text),
		&genai.GenerateContentConfig{
			SystemInstruction: &genai.Content{Parts: []*genai.Part{{Text: SYSTEM_INSTRUCTION}}},
		},
	)
	if err != nil {
		return nil, err
	}

	var summary SummarizeResult
	if err := json.Unmarshal([]byte(result.Text()), &summary); err != nil {
		return nil, err
	}
	return &summary, nil
}
