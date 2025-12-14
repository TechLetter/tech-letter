package dto

type ChatbotChatRequestDTO struct {
	Query string `json:"query" binding:"required" example:"벡터 DB는 어떤 원리로 동작하나요?"`
}

type ChatbotChatResponseDTO struct {
	Answer string `json:"answer"`
}
