package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"

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
		})
	}
}
