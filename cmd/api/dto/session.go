package dto

import "time"

// ChatMessage represents a single message in a chat session.
type ChatMessage struct {
	Role      string    `json:"role"`
	Content   string    `json:"content"`
	CreatedAt time.Time `json:"created_at"`
}

// ChatSession represents a chat session.
type ChatSession struct {
	ID        string        `json:"id"`
	UserCode  string        `json:"user_code"`
	Title     string        `json:"title"`
	Messages  []ChatMessage `json:"messages"`
	CreatedAt time.Time     `json:"created_at"`
	UpdatedAt time.Time     `json:"updated_at"`
}

// CreateSessionResponse is the response from creating a session.
type CreateSessionResponse ChatSession

// ListSessionsResponse is the paginated response for listing sessions.
type ListSessionsResponse struct {
	Total    int64         `json:"total"`
	Page     int           `json:"page"`
	PageSize int           `json:"page_size"`
	Items    []ChatSession `json:"items"`
}
