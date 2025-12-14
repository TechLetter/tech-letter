package services

import (
	"context"
	"errors"
	"net/http"

	"tech-letter/cmd/api/clients/chatbotclient"
	"tech-letter/cmd/api/dto"
)

type ChatbotService struct {
	client *chatbotclient.Client
}

type ChatbotChatError struct {
	StatusCode int
	ErrorCode  string
	Cause      error
}

func (e *ChatbotChatError) Error() string {
	if e == nil {
		return "chatbot_failed"
	}
	return e.ErrorCode
}

func NewChatbotService(client *chatbotclient.Client) *ChatbotService {
	return &ChatbotService{client: client}
}

func (s *ChatbotService) Chat(ctx context.Context, query string) (dto.ChatbotChatResponseDTO, *ChatbotChatError) {
	resp, err := s.client.Chat(ctx, query)
	if err != nil {
		var httpErr *chatbotclient.HTTPError
		if errors.As(err, &httpErr) {
			normalizedStatus, normalizedErrorCode := normalizeChatbotStatus(httpErr.StatusCode)
			return dto.ChatbotChatResponseDTO{}, &ChatbotChatError{StatusCode: normalizedStatus, ErrorCode: normalizedErrorCode, Cause: err}
		}
		return dto.ChatbotChatResponseDTO{}, &ChatbotChatError{StatusCode: http.StatusInternalServerError, ErrorCode: "chatbot_failed", Cause: err}
	}

	return dto.ChatbotChatResponseDTO{Answer: resp.Answer}, nil
}

func normalizeChatbotStatus(statusCode int) (normalizedStatus int, errorCode string) {
	switch statusCode {
	case http.StatusTooManyRequests:
		return http.StatusTooManyRequests, "rate_limited"
	case http.StatusBadRequest, http.StatusUnprocessableEntity:
		return http.StatusBadRequest, "invalid_request"
	case http.StatusServiceUnavailable, http.StatusBadGateway, http.StatusGatewayTimeout:
		return http.StatusServiceUnavailable, "chatbot_unavailable"
	default:
		return http.StatusInternalServerError, "chatbot_failed"
	}
}
