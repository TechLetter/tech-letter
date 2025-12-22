package dto

type ChatbotChatRequestDTO struct {
	Query     string `json:"query" binding:"required" example:"벡터 DB는 어떤 원리로 동작하나요?"`
	SessionID string `json:"session_id,omitempty"` // Optional for first message (will create new session if empty, but client should create session first ideally)
}

type ChatbotChatResponseDTO struct {
	Answer           string `json:"answer"`
	ConsumedCredits  int    `json:"consumed_credits"`
	RemainingCredits int    `json:"remaining_credits"`
}
