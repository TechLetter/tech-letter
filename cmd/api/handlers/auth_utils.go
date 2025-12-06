package handlers

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/services"
)

// requireUserCodeFromHeader는 Authorization 헤더가 필수인 엔드포인트에서
// JWT를 파싱하여 user_code를 추출한다. 실패 시 적절한 401 에러 응답을 내려주고 false를 반환한다.
func requireUserCodeFromHeader(c *gin.Context, authSvc *services.AuthService) (string, bool) {
	authHeader := c.GetHeader("Authorization")
	if authHeader == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing_authorization_header"})
		return "", false
	}

	parts := strings.SplitN(authHeader, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid_authorization_header"})
		return "", false
	}

	token := strings.TrimSpace(parts[1])
	if token == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "empty_token"})
		return "", false
	}

	userCode, _, err := authSvc.ParseAccessToken(token)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid_token"})
		return "", false
	}

	return userCode, true
}

// optionalUserCodeFromHeader는 Authorization 헤더가 선택인 엔드포인트에서 사용한다.
// - 토큰이 없으면 (익명 요청) hasToken=false, ok=true 를 반환한다.
// - 토큰이 있으나 유효하지 않으면 401 에러 응답을 내려주고 hasToken=true, ok=false 를 반환한다.
// - 유효한 토큰이면 userCode와 함께 hasToken=true, ok=true 를 반환한다.
func optionalUserCodeFromHeader(c *gin.Context, authSvc *services.AuthService) (userCode string, hasToken bool, ok bool) {
	authHeader := c.GetHeader("Authorization")
	if authHeader == "" {
		return "", false, true
	}

	parts := strings.SplitN(authHeader, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid_authorization_header"})
		return "", true, false
	}

	token := strings.TrimSpace(parts[1])
	if token == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "empty_token"})
		return "", true, false
	}

	userCode, _, err := authSvc.ParseAccessToken(token)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid_token"})
		return "", true, false
	}

	return userCode, true, true
}
