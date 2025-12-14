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
	Query string `json:"query"`
}

type SourceInfo struct {
	Title    string  `json:"title"`
	BlogName string  `json:"blog_name"`
	Link     string  `json:"link"`
	Score    float64 `json:"score"`
}

type ChatResponse struct {
	Answer  string       `json:"answer"`
	Sources []SourceInfo `json:"sources"`
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

func (c *Client) Chat(ctx context.Context, query string) (ChatResponse, error) {
	payload := ChatRequest{Query: query}
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
