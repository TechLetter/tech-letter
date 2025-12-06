package dto

// ErrorResponseDTO는 공통 에러 응답 형식을 통일하기 위한 DTO이다.
type ErrorResponseDTO struct {
	Error string `json:"error" example:"invalid_token"`
}

// MessageResponseDTO는 단순 메시지 응답 형식을 통일하기 위한 DTO이다.
type MessageResponseDTO struct {
	Message string `json:"message" example:"view count incremented successfully"`
}
