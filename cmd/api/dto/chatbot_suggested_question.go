package dto

import "time"

type ChatbotSuggestedQuestionDTO struct {
	ID        string    `json:"id"`
	Text      string    `json:"text"`
	SortOrder int       `json:"sort_order"`
	IsActive  bool      `json:"is_active"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type ChatbotSuggestedQuestionMutationDTO struct {
	Text      string `json:"text" binding:"required"`
	SortOrder int    `json:"sort_order"`
	IsActive  *bool  `json:"is_active,omitempty"`
}
