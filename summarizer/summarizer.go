package summarizer

import (
	"context"
	"encoding/json"
	"tech-letter/config"

	"google.golang.org/genai"
)

type SummarizeResult struct {
	SummaryShort string `json:"summary_short"`
	SummaryLong  string `json:"summary_long"`
	IsFailure    bool   `json:"is_failure"`
}

const SYSTEM_INSTRUCTION = `
You are a content summarization assistant for technical blog posts. Your task is to analyze the provided text and produce a structured summary.
The response MUST be a valid JSON object with three keys:
1.  summary_short: A concise summary of the blog post, no more than 200 characters.
2.  summary_long: A detailed summary of the blog post, no more than 1000 characters.
3.  is_failure: A boolean value. Set to true if the content contains a security check (e.g., "I'm not a bot," "Are you human?") that prevents summarization. Otherwise, set to false.
You MUST NOT wrap the JSON output in a markdown code block (e.g., ` + "```json ... ```" + `). The response should contain ONLY the raw JSON string.
If summarization fails, set is_failure to true and provide an empty string for both summary_short and summary_long.
All responses, including all string values within the JSON object, MUST be written in Korean.
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
