package chatbotclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"tech-letter/cmd/api/httpclient"
)

type Client struct {
	base *httpclient.BaseClient
}

type ChatRequest struct {
	Query     string        `json:"query"`
	SessionID string        `json:"session_id,omitempty"`
	Messages  []ChatMessage `json:"messages,omitempty"`
	Memory    *ChatMemory   `json:"memory,omitempty"`
}

type ChatMessage struct {
	Role      string                 `json:"role"`
	Content   string                 `json:"content"`
	CreatedAt time.Time              `json:"created_at"`
	Metadata  map[string]interface{} `json:"metadata,omitempty"`
}

type ChatMemory struct {
	Summary             string `json:"summary"`
	CoveredMessageCount int    `json:"covered_message_count"`
	Status              string `json:"status"`
}

type SourceInfo struct {
	Title    string  `json:"title"`
	BlogName string  `json:"blog_name"`
	Link     string  `json:"link"`
	Score    float64 `json:"score"`
}

type ChatResponse struct {
	Answer             string          `json:"answer"`
	Sources            []SourceInfo    `json:"sources"`
	Agent              *AgentMetadata  `json:"agent,omitempty"`
	Guard              *GuardMetadata  `json:"guard,omitempty"`
	Memory             *MemoryMetadata `json:"memory,omitempty"`
	SuggestedQuestions []string        `json:"suggested_questions,omitempty"`
}

type AgentActivity struct {
	Type   string `json:"type"`
	Label  string `json:"label"`
	Status string `json:"status"`
}

type AgentMetadata struct {
	Mode       string          `json:"mode"`
	Intent     string          `json:"intent"`
	Activities []AgentActivity `json:"activities"`
}

type GuardMetadata struct {
	Action    string   `json:"action"`
	RiskLevel string   `json:"risk_level"`
	Message   string   `json:"message,omitempty"`
	Findings  []string `json:"findings,omitempty"`
}

type MemoryMetadata struct {
	Used                bool   `json:"used"`
	Compressed          bool   `json:"compressed"`
	CompressionFailed   bool   `json:"compression_failed,omitempty"`
	Strategy            string `json:"strategy"`
	SummaryMessageCount int    `json:"summary_message_count"`
	RecentMessageCount  int    `json:"recent_message_count"`
	HistoryMessageCount int    `json:"history_message_count"`
	Rewritten           bool   `json:"rewritten"`
	Status              string `json:"status"`
}

type HTTPError struct {
	StatusCode int
	Body       string
}

func (e *HTTPError) Error() string {
	return fmt.Sprintf("chatbot-service request failed: status=%d body=%s", e.StatusCode, e.Body)
}

func New() *Client {
	base := os.Getenv("CHATBOT_SERVICE_BASE_URL")
	if base == "" {
		base = "http://chatbot_service:8003"
	}

	httpClient := httpclient.New(httpclient.Config{Timeout: 5 * time.Minute})
	return &Client{base: httpclient.NewBaseClientWithClient(httpClient, base)}
}

func (c *Client) Chat(ctx context.Context, query, sessionID string, messages []ChatMessage, memory *ChatMemory) (ChatResponse, error) {
	payload := ChatRequest{
		Query:     query,
		SessionID: sessionID,
		Messages:  messages,
		Memory:    memory,
	}
	buf, err := json.Marshal(payload)
	if err != nil {
		return ChatResponse{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/chat", nil, bytes.NewReader(buf))
	if err != nil {
		return ChatResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return ChatResponse{}, err
	}
	defer resp.Body.Close()

	const maxBodySize = 5 * 1024 * 1024
	body, readErr := io.ReadAll(io.LimitReader(resp.Body, maxBodySize))
	if readErr != nil {
		return ChatResponse{}, fmt.Errorf("chatbot-service response read failed: %w", readErr)
	}

	if resp.StatusCode != http.StatusOK {
		return ChatResponse{}, &HTTPError{StatusCode: resp.StatusCode, Body: string(body)}
	}

	var out ChatResponse
	if err := json.Unmarshal(body, &out); err != nil {
		return ChatResponse{}, err
	}
	return out, nil
}
