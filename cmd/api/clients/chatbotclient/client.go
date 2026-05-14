package chatbotclient

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
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
	Answer  string          `json:"answer"`
	Sources []SourceInfo    `json:"sources"`
	Agent   *AgentMetadata  `json:"agent,omitempty"`
	Guard   *GuardMetadata  `json:"guard,omitempty"`
	Memory  *MemoryMetadata `json:"memory,omitempty"`
}

type StreamEvent struct {
	Event string
	Data  json.RawMessage
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

func (c *Client) StreamChat(
	ctx context.Context,
	query string,
	sessionID string,
	messages []ChatMessage,
	memory *ChatMemory,
	handleEvent func(StreamEvent) error,
) error {
	payload := ChatRequest{
		Query:     query,
		SessionID: sessionID,
		Messages:  messages,
		Memory:    memory,
	}
	buf, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/chat/stream", nil, bytes.NewReader(buf))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	resp, err := c.base.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return &HTTPError{StatusCode: resp.StatusCode, Body: string(body)}
	}

	return readStreamEvents(resp.Body, handleEvent)
}

func readStreamEvents(reader io.Reader, handleEvent func(StreamEvent) error) error {
	bufReader := bufio.NewReader(reader)
	eventName := "message"
	dataLines := make([]string, 0, 1)

	dispatch := func() error {
		if len(dataLines) == 0 {
			eventName = "message"
			return nil
		}
		payload := strings.Join(dataLines, "\n")
		event := StreamEvent{
			Event: eventName,
			Data:  json.RawMessage(payload),
		}
		eventName = "message"
		dataLines = dataLines[:0]
		return handleEvent(event)
	}

	for {
		line, err := bufReader.ReadString('\n')
		if err != nil && len(line) == 0 {
			if err == io.EOF {
				return dispatch()
			}
			return err
		}

		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			if dispatchErr := dispatch(); dispatchErr != nil {
				return dispatchErr
			}
		} else if strings.HasPrefix(line, "event:") {
			eventName = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		} else if strings.HasPrefix(line, "data:") {
			data := strings.TrimPrefix(line, "data:")
			if strings.HasPrefix(data, " ") {
				data = data[1:]
			}
			dataLines = append(dataLines, data)
		}

		if err == io.EOF {
			return dispatch()
		}
	}
}
