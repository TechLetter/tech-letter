package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/clients/chatbotclient"
	"tech-letter/cmd/api/dto"
	"tech-letter/cmd/api/services"
)

// ChatbotChatHandler godoc
// @Summary      챗봇 질의
// @Description  로그인된 사용자만 사용할 수 있는 챗봇 질의 API. 크레딧이 차감된다.
// @Tags         chatbot
// @Security     BearerAuth
// @Accept       json
// @Produce      json
// @Param        body  body      dto.ChatbotChatRequestDTO  true  "chat request"
// @Success      200   {object}  dto.ChatbotChatResponseDTO
// @Failure      400   {object}  dto.ErrorResponseDTO
// @Failure      401   {object}  dto.ErrorResponseDTO
// @Failure      402   {object}  dto.ErrorResponseDTO  "크레딧 부족"
// @Failure      429   {object}  dto.ErrorResponseDTO
// @Failure      503   {object}  dto.ErrorResponseDTO
// @Failure      500   {object}  dto.ErrorResponseDTO
// @Router       /chatbot/chat [post]
func ChatbotChatHandler(
	chatbotSvc *services.ChatbotService,
	authSvc *services.AuthService,
) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		var req dto.ChatbotChatRequestDTO
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: "invalid_request"})
			return
		}

		// Service에서 크레딧 차감, 채팅 요청, 로그 기록을 통합 처리
		result, chatErr := chatbotSvc.ChatWithCredits(c.Request.Context(), userCode, req.Query, req.SessionID)
		if chatErr != nil {
			c.JSON(chatErr.StatusCode, dto.ErrorResponseDTO{Error: chatErr.ErrorCode})
			return
		}

		c.JSON(http.StatusOK, dto.ChatbotChatResponseDTO{
			Answer:           result.Answer,
			ConsumedCredits:  result.ConsumedCredits,
			RemainingCredits: result.RemainingCredits,
			Sources:          mapChatbotSources(result.Sources),
			Agent:            mapChatbotAgent(result.Agent),
			Guard:            mapChatbotGuard(result.Guard),
			Memory:           mapChatbotMemory(result.Memory),
		})
	}
}

// ChatbotChatStreamHandler godoc
// @Summary      챗봇 질의 스트림
// @Description  챗봇 처리 과정을 SSE로 먼저 전달하고, 최종 답변은 done 이벤트로 전달한다.
// @Tags         chatbot
// @Security     BearerAuth
// @Accept       json
// @Produce      text/event-stream
// @Param        body  body  dto.ChatbotChatRequestDTO  true  "chat request"
// @Router       /chatbot/chat/stream [post]
func ChatbotChatStreamHandler(
	chatbotSvc *services.ChatbotService,
	authSvc *services.AuthService,
) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		var req dto.ChatbotChatRequestDTO
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: "invalid_request"})
			return
		}

		prepared, chatErr := chatbotSvc.PrepareChatWithCredits(c.Request.Context(), userCode, req.Query, req.SessionID)
		if chatErr != nil {
			c.JSON(chatErr.StatusCode, dto.ErrorResponseDTO{Error: chatErr.ErrorCode})
			return
		}

		flusher, ok := c.Writer.(http.Flusher)
		if !ok {
			chatbotSvc.FailPreparedChat(detachedContext(), prepared, "streaming_unsupported")
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: "streaming_unsupported"})
			return
		}

		header := c.Writer.Header()
		header.Set("Content-Type", "text/event-stream")
		header.Set("Cache-Control", "no-cache")
		header.Set("Connection", "keep-alive")
		header.Set("X-Accel-Buffering", "no")
		c.Status(http.StatusOK)
		flusher.Flush()

		doneSent := false
		errorSent := false
		streamErr := chatbotSvc.StreamPreparedChat(c.Request.Context(), prepared, func(event chatbotclient.StreamEvent) error {
			switch event.Event {
			case "done":
				var resp chatbotclient.ChatResponse
				if err := json.Unmarshal(event.Data, &resp); err != nil {
					return err
				}
				donePayload := dto.ChatbotChatResponseDTO{
					Answer:           resp.Answer,
					ConsumedCredits:  1,
					RemainingCredits: prepared.Credit.Remaining,
					Sources:          mapChatbotSources(resp.Sources),
					Agent:            mapChatbotAgent(resp.Agent),
					Guard:            mapChatbotGuard(resp.Guard),
					Memory:           mapChatbotMemory(resp.Memory),
				}
				if err := writeChatbotSSE(c, flusher, "done", donePayload); err != nil {
					return err
				}
				doneSent = true
				chatbotSvc.CompletePreparedChat(detachedContext(), prepared, resp)
				return nil
			case "error":
				errorSent = true
				chatbotSvc.FailPreparedChat(detachedContext(), prepared, chatbotStreamErrorCode(event.Data))
				return writeRawChatbotSSE(c, flusher, "error", event.Data)
			default:
				return writeRawChatbotSSE(c, flusher, event.Event, event.Data)
			}
		})

		if streamErr != nil && !doneSent && !errorSent {
			_, errorCode := services.NormalizeChatbotError(streamErr)
			chatbotSvc.FailPreparedChat(detachedContext(), prepared, errorCode)
			_ = writeChatbotSSE(c, flusher, "error", gin.H{
				"code":    errorCode,
				"message": chatbotStreamErrorMessage(errorCode),
			})
		}
	}
}

func writeChatbotSSE(c *gin.Context, flusher http.Flusher, event string, payload any) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	return writeRawChatbotSSE(c, flusher, event, data)
}

func writeRawChatbotSSE(c *gin.Context, flusher http.Flusher, event string, data json.RawMessage) error {
	if len(data) == 0 {
		data = json.RawMessage("{}")
	}
	if _, err := fmt.Fprintf(c.Writer, "event: %s\ndata: %s\n\n", event, data); err != nil {
		return err
	}
	flusher.Flush()
	return nil
}

func chatbotStreamErrorCode(data json.RawMessage) string {
	var payload struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(data, &payload); err != nil || payload.Code == "" {
		return "chatbot_failed"
	}
	return payload.Code
}

func chatbotStreamErrorMessage(code string) string {
	switch code {
	case "policy_blocked":
		return "요청에 내부 지시 변경 또는 민감 정보 요청으로 해석될 수 있는 내용이 포함되어 처리하지 않았습니다."
	case "rate_limited":
		return "AI API 호출이 일시적으로 제한되었습니다. 잠시 후 다시 시도해주세요."
	case "chatbot_unavailable":
		return "AI 서버가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요."
	default:
		return "채팅 요청 처리 중 오류가 발생했습니다."
	}
}

func detachedContext() context.Context {
	return context.Background()
}

func mapChatbotSources(sources []chatbotclient.SourceInfo) []dto.ChatbotSourceInfoDTO {
	out := make([]dto.ChatbotSourceInfoDTO, 0, len(sources))
	for _, source := range sources {
		out = append(out, dto.ChatbotSourceInfoDTO{
			Title:    source.Title,
			BlogName: source.BlogName,
			Link:     source.Link,
			Score:    source.Score,
		})
	}
	return out
}

func mapChatbotAgent(agent *chatbotclient.AgentMetadata) *dto.ChatbotAgentMetadataDTO {
	if agent == nil {
		return nil
	}
	activities := make([]dto.ChatbotAgentActivityDTO, 0, len(agent.Activities))
	for _, activity := range agent.Activities {
		activities = append(activities, dto.ChatbotAgentActivityDTO{
			Type:   activity.Type,
			Label:  activity.Label,
			Status: activity.Status,
		})
	}
	return &dto.ChatbotAgentMetadataDTO{
		Mode:       agent.Mode,
		Intent:     agent.Intent,
		Activities: activities,
	}
}

func mapChatbotGuard(guard *chatbotclient.GuardMetadata) *dto.ChatbotGuardMetadataDTO {
	if guard == nil {
		return nil
	}
	return &dto.ChatbotGuardMetadataDTO{
		Action:    guard.Action,
		RiskLevel: guard.RiskLevel,
		Message:   guard.Message,
		Findings:  guard.Findings,
	}
}

func mapChatbotMemory(memory *chatbotclient.MemoryMetadata) *dto.ChatbotMemoryMetadataDTO {
	if memory == nil {
		return nil
	}
	return &dto.ChatbotMemoryMetadataDTO{
		Used:                memory.Used,
		Compressed:          memory.Compressed,
		CompressionFailed:   memory.CompressionFailed,
		Strategy:            memory.Strategy,
		SummaryMessageCount: memory.SummaryMessageCount,
		RecentMessageCount:  memory.RecentMessageCount,
		HistoryMessageCount: memory.HistoryMessageCount,
		Rewritten:           memory.Rewritten,
		Status:              memory.Status,
	}
}
