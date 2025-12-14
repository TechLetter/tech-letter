package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/dto"
	"tech-letter/cmd/api/services"
)

// ChatbotChatHandler godoc
// @Summary      챗봇 질의
// @Description  로그인된 사용자만 사용할 수 있는 챗봇 질의 API. API Gateway가 chatbot-service로 프록시한다.
// @Tags         chatbot
// @Param        Authorization  header  string  true   "Bearer 액세스 토큰 (예: Bearer eyJ...)"
// @Accept       json
// @Produce      json
// @Param        body  body      dto.ChatbotChatRequestDTO  true  "chat request"
// @Success      200   {object}  dto.ChatbotChatResponseDTO
// @Failure      400   {object}  dto.ErrorResponseDTO
// @Failure      401   {object}  dto.ErrorResponseDTO
// @Failure      429   {object}  dto.ErrorResponseDTO
// @Failure      503   {object}  dto.ErrorResponseDTO
// @Failure      500   {object}  dto.ErrorResponseDTO
// @Router       /chatbot/chat [post]
func ChatbotChatHandler(chatbotSvc *services.ChatbotService, authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		_, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		var req dto.ChatbotChatRequestDTO
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: "invalid_request"})
			return
		}

		result, chatErr := chatbotSvc.Chat(c.Request.Context(), req.Query)
		if chatErr != nil {
			c.JSON(chatErr.StatusCode, dto.ErrorResponseDTO{Error: chatErr.ErrorCode})
			return
		}
		c.JSON(http.StatusOK, result)
	}
}
