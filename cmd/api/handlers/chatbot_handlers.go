package handlers

import (
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
