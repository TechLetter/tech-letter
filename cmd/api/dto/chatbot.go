package dto

type ChatbotChatRequestDTO struct {
	Query     string `json:"query" binding:"required" example:"벡터 DB는 어떤 원리로 동작하나요?"`
	SessionID string `json:"session_id,omitempty"` // Optional for first message (will create new session if empty, but client should create session first ideally)
}

type ChatbotSourceInfoDTO struct {
	Title    string  `json:"title"`
	BlogName string  `json:"blog_name"`
	Link     string  `json:"link"`
	Score    float64 `json:"score"`
}

type ChatbotAgentActivityDTO struct {
	Type   string `json:"type"`
	Label  string `json:"label"`
	Status string `json:"status"`
}

type ChatbotAgentMetadataDTO struct {
	Mode       string                    `json:"mode"`
	Intent     string                    `json:"intent"`
	Activities []ChatbotAgentActivityDTO `json:"activities"`
}

type ChatbotGuardMetadataDTO struct {
	Action    string   `json:"action"`
	RiskLevel string   `json:"risk_level"`
	Message   string   `json:"message,omitempty"`
	Findings  []string `json:"findings,omitempty"`
}

type ChatbotMemoryMetadataDTO struct {
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

type ChatbotChatResponseDTO struct {
	Answer             string                    `json:"answer"`
	ConsumedCredits    int                       `json:"consumed_credits"`
	RemainingCredits   int                       `json:"remaining_credits"`
	Sources            []ChatbotSourceInfoDTO    `json:"sources"`
	Agent              *ChatbotAgentMetadataDTO  `json:"agent,omitempty"`
	Guard              *ChatbotGuardMetadataDTO  `json:"guard,omitempty"`
	Memory             *ChatbotMemoryMetadataDTO `json:"memory,omitempty"`
	SuggestedQuestions []string                  `json:"suggested_questions,omitempty"`
}
