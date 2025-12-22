package handlers

import (
	"net/http"
	"strconv"

	"tech-letter/cmd/api/dto"
	"tech-letter/cmd/api/services"

	"github.com/gin-gonic/gin"
)

// ListSessionsHandler godoc
// @Summary      대화 세션 목록 조회
// @Description  사용자의 대화 세션 목록을 페이지네이션하여 조회합니다.
// @Tags         chatbot
// @Security     BearerAuth
// @Produce      json
// @Param        page      query     int     false  "페이지 번호 (기본 1)"
// @Param        page_size query     int     false  "페이지 크기 (기본 20)"
// @Success      200       {object}  dto.ListSessionsResponse
// @Router       /chatbot/sessions [get]
func ListSessionsHandler(authSvc *services.AuthService, userSvc *services.UserService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))

		resp, err := userSvc.ListSessions(c.Request.Context(), userCode, page, pageSize)
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}

		c.JSON(http.StatusOK, resp)
	}
}

// GetSessionHandler godoc
// @Summary      대화 세션 상세 조회
// @Description  특정 대화 세션의 상세 정보(메시지 목록 포함)를 조회합니다.
// @Tags         chatbot
// @Security     BearerAuth
// @Produce      json
// @Param        id   path      string  true  "세션 ID"
// @Success      200  {object}  dto.ChatSession
// @Failure      404  {object}  dto.ErrorResponseDTO
// @Router       /chatbot/sessions/{id} [get]
func GetSessionHandler(authSvc *services.AuthService, userSvc *services.UserService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		sessionID := c.Param("id")
		session, err := userSvc.GetSession(c.Request.Context(), userCode, sessionID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		if session == nil {
			c.JSON(http.StatusNotFound, dto.ErrorResponseDTO{Error: "session not found"})
			return
		}

		c.JSON(http.StatusOK, session)
	}
}

// DeleteSessionHandler godoc
// @Summary      대화 세션 삭제
// @Description  특정 대화 세션을 삭제합니다.
// @Tags         chatbot
// @Security     BearerAuth
// @Produce      json
// @Param        id   path      string  true  "세션 ID"
// @Success      200  {object}  dto.MessageResponseDTO
// @Router       /chatbot/sessions/{id} [delete]
func DeleteSessionHandler(authSvc *services.AuthService, userSvc *services.UserService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		sessionID := c.Param("id")
		err := userSvc.DeleteSession(c.Request.Context(), userCode, sessionID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}

		c.JSON(http.StatusOK, dto.MessageResponseDTO{Message: "deleted"})
	}
}

// CreateSessionHandler godoc
// @Summary      대화 세션 생성
// @Description  빈 대화 세션을 생성합니다. (UI에서 '+ 새 채팅' 버튼 클릭 시)
// @Tags         chatbot
// @Security     BearerAuth
// @Produce      json
// @Success      200  {object}  dto.ChatSession
// @Router       /chatbot/sessions [post]
func CreateSessionHandler(authSvc *services.AuthService, userSvc *services.UserService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		session, err := userSvc.CreateSession(c.Request.Context(), userCode)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		c.JSON(http.StatusOK, session)
	}
}
