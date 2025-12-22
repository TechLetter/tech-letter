package services

import (
	"context"
	"errors"
	"net/http"

	"tech-letter/cmd/api/clients/chatbotclient"
	"tech-letter/cmd/api/clients/userclient"
)

// ChatResult는 채팅 요청의 통합 결과를 담는다.
type ChatResult struct {
	Answer           string
	ConsumedCredits  int
	RemainingCredits int
}

type ChatbotService struct {
	chatbotClient *chatbotclient.Client
	userClient    *userclient.Client
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

func NewChatbotService(chatbotClient *chatbotclient.Client, userClient *userclient.Client) *ChatbotService {
	return &ChatbotService{chatbotClient: chatbotClient, userClient: userClient}
}

// ChatWithCredits는 크레딧 차감, 채팅 요청, 로그 기록을 통합 처리한다.
func (s *ChatbotService) ChatWithCredits(ctx context.Context, userCode, query, sessionID string) (*ChatResult, *ChatbotChatError) {
	// 1. session_id가 제공된 경우 유효성 검증
	if sessionID != "" {
		session, err := s.userClient.GetSession(ctx, userCode, sessionID)
		if err != nil || session == nil {
			return nil, &ChatbotChatError{StatusCode: http.StatusBadRequest, ErrorCode: "invalid_session_id", Cause: err}
		}
	}

	// 2. 크레딧 차감
	creditResp, err := s.userClient.ConsumeCreditsWithID(ctx, userCode, 1, "chat")
	if err != nil {
		if errors.Is(err, userclient.ErrInsufficientCredits) {
			return nil, &ChatbotChatError{StatusCode: http.StatusPaymentRequired, ErrorCode: "insufficient_credits", Cause: err}
		}
		return nil, &ChatbotChatError{StatusCode: http.StatusInternalServerError, ErrorCode: "credit_service_error", Cause: err}
	}

	// 3. 채팅 요청
	resp, chatErr := s.chatbotClient.Chat(ctx, query)
	if chatErr != nil {
		var httpErr *chatbotclient.HTTPError
		normalizedStatus, normalizedErrorCode := http.StatusInternalServerError, "chatbot_failed"
		if errors.As(chatErr, &httpErr) {
			normalizedStatus, normalizedErrorCode = normalizeChatbotStatus(httpErr.StatusCode)
		}

		// 채팅 실패 시 환불 + 로그
		_, _ = s.userClient.LogChatFailed(
			ctx,
			userCode,
			creditResp.ConsumeID,
			creditResp.ConsumedCreditIDs,
			query,
			normalizedErrorCode,
			sessionID,
		)
		return nil, &ChatbotChatError{StatusCode: normalizedStatus, ErrorCode: normalizedErrorCode, Cause: chatErr}
	}

	// 4. 채팅 성공 시 로그
	_, _ = s.userClient.LogChatCompleted(
		ctx,
		userCode,
		creditResp.ConsumeID,
		creditResp.ConsumedCreditIDs,
		query,
		resp.Answer,
		sessionID,
	)

	return &ChatResult{
		Answer:           resp.Answer,
		ConsumedCredits:  1,
		RemainingCredits: creditResp.Remaining,
	}, nil
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
