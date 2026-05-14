package services

import (
	"context"
	"errors"
	"net/http"

	"tech-letter/cmd/api/clients/chatbotclient"
	"tech-letter/cmd/api/clients/userclient"
	"tech-letter/cmd/api/dto"
)

// ChatResult는 채팅 요청의 통합 결과를 담는다.
type ChatResult struct {
	Answer           string
	ConsumedCredits  int
	RemainingCredits int
	Sources          []chatbotclient.SourceInfo
	Agent            *chatbotclient.AgentMetadata
	Guard            *chatbotclient.GuardMetadata
	Memory           *chatbotclient.MemoryMetadata
}

type PreparedChat struct {
	UserCode  string
	Query     string
	SessionID string
	Session   *dto.ChatSession
	Credit    userclient.ConsumeCreditsResponse
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
	prepared, prepareErr := s.PrepareChatWithCredits(ctx, userCode, query, sessionID)
	if prepareErr != nil {
		return nil, prepareErr
	}

	resp, chatErr := s.chatbotClient.Chat(
		ctx,
		query,
		sessionID,
		buildChatbotHistory(prepared.Session),
		buildChatbotMemory(prepared.Session),
	)
	if chatErr != nil {
		normalizedStatus, normalizedErrorCode := NormalizeChatbotError(chatErr)
		s.FailPreparedChat(ctx, prepared, normalizedErrorCode)
		return nil, &ChatbotChatError{StatusCode: normalizedStatus, ErrorCode: normalizedErrorCode, Cause: chatErr}
	}

	return s.CompletePreparedChat(ctx, prepared, resp), nil
}

func (s *ChatbotService) PrepareChatWithCredits(ctx context.Context, userCode, query, sessionID string) (*PreparedChat, *ChatbotChatError) {
	guardResult := EvaluateChatbotPrompt(query)
	if guardResult.Blocked {
		statusCode := http.StatusForbidden
		if guardResult.ErrorCode == "invalid_request" {
			statusCode = http.StatusBadRequest
		}
		return nil, &ChatbotChatError{StatusCode: statusCode, ErrorCode: guardResult.ErrorCode}
	}

	var session *dto.ChatSession

	// 1. session_id가 제공된 경우 유효성 검증
	if sessionID != "" {
		currentSession, err := s.userClient.GetSession(ctx, userCode, sessionID)
		if err != nil || currentSession == nil {
			return nil, &ChatbotChatError{StatusCode: http.StatusBadRequest, ErrorCode: "invalid_session_id", Cause: err}
		}
		session = currentSession
	}

	// 2. 크레딧 차감
	creditResp, err := s.userClient.ConsumeCreditsWithID(ctx, userCode, 1, "chat")
	if err != nil {
		if errors.Is(err, userclient.ErrInsufficientCredits) {
			return nil, &ChatbotChatError{StatusCode: http.StatusPaymentRequired, ErrorCode: "insufficient_credits", Cause: err}
		}
		return nil, &ChatbotChatError{StatusCode: http.StatusInternalServerError, ErrorCode: "credit_service_error", Cause: err}
	}

	return &PreparedChat{
		UserCode:  userCode,
		Query:     query,
		SessionID: sessionID,
		Session:   session,
		Credit:    creditResp,
	}, nil
}

func (s *ChatbotService) StreamPreparedChat(
	ctx context.Context,
	prepared *PreparedChat,
	handleEvent func(chatbotclient.StreamEvent) error,
) error {
	return s.chatbotClient.StreamChat(
		ctx,
		prepared.Query,
		prepared.SessionID,
		buildChatbotHistory(prepared.Session),
		buildChatbotMemory(prepared.Session),
		handleEvent,
	)
}

func (s *ChatbotService) CompletePreparedChat(ctx context.Context, prepared *PreparedChat, resp chatbotclient.ChatResponse) *ChatResult {
	_, _ = s.userClient.LogChatCompleted(
		ctx,
		prepared.UserCode,
		prepared.Credit.ConsumeID,
		prepared.Credit.ConsumedCreditIDs,
		prepared.Query,
		resp.Answer,
		prepared.SessionID,
		buildChatMetadata(resp),
	)

	return &ChatResult{
		Answer:           resp.Answer,
		ConsumedCredits:  1,
		RemainingCredits: prepared.Credit.Remaining,
		Sources:          resp.Sources,
		Agent:            resp.Agent,
		Guard:            resp.Guard,
		Memory:           resp.Memory,
	}
}

func (s *ChatbotService) FailPreparedChat(ctx context.Context, prepared *PreparedChat, errorCode string) {
	_, _ = s.userClient.LogChatFailed(
		ctx,
		prepared.UserCode,
		prepared.Credit.ConsumeID,
		prepared.Credit.ConsumedCreditIDs,
		prepared.Query,
		errorCode,
		prepared.SessionID,
	)
}

func NormalizeChatbotError(err error) (normalizedStatus int, errorCode string) {
	var httpErr *chatbotclient.HTTPError
	if errors.As(err, &httpErr) {
		return normalizeChatbotStatus(httpErr.StatusCode)
	}
	return http.StatusInternalServerError, "chatbot_failed"
}

func normalizeChatbotStatus(statusCode int) (normalizedStatus int, errorCode string) {
	switch statusCode {
	case http.StatusForbidden:
		return http.StatusForbidden, "policy_blocked"
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

func buildChatbotHistory(session *dto.ChatSession) []chatbotclient.ChatMessage {
	if session == nil || len(session.Messages) == 0 {
		return nil
	}

	const maxHistoryMessages = 60
	messages := session.Messages
	if len(messages) > maxHistoryMessages {
		messages = messages[len(messages)-maxHistoryMessages:]
	}

	out := make([]chatbotclient.ChatMessage, 0, len(messages))
	for _, message := range messages {
		if message.Role != "user" && message.Role != "assistant" {
			continue
		}
		out = append(out, chatbotclient.ChatMessage{
			Role:      message.Role,
			Content:   message.Content,
			CreatedAt: message.CreatedAt,
			Metadata:  message.Metadata,
		})
	}
	return out
}

func buildChatbotMemory(session *dto.ChatSession) *chatbotclient.ChatMemory {
	if session == nil || session.Memory == nil {
		return nil
	}
	return &chatbotclient.ChatMemory{
		Summary:             session.Memory.Summary,
		CoveredMessageCount: session.Memory.CoveredMessageCount,
		Status:              session.Memory.Status,
	}
}

func buildChatMetadata(resp chatbotclient.ChatResponse) map[string]interface{} {
	metadata := map[string]interface{}{}
	if len(resp.Sources) > 0 {
		metadata["sources"] = resp.Sources
	}
	if resp.Agent != nil {
		metadata["agent"] = resp.Agent
	}
	if resp.Guard != nil {
		metadata["guard"] = resp.Guard
	}
	if resp.Memory != nil {
		metadata["memory"] = resp.Memory
	}
	if len(metadata) == 0 {
		return nil
	}
	return metadata
}
