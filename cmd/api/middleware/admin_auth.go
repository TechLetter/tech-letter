package middleware

import (
	"log"
	"net/http"

	"tech-letter/cmd/api/auth"
	"tech-letter/cmd/api/services"

	"github.com/gin-gonic/gin"
)

// AdminAuthMiddleware 는 요청 헤더의 JWT를 검증하고, role이 'admin'인지 확인합니다.
func AdminAuthMiddleware(authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		token, err := auth.ExtractBearerToken(c)
		if err != nil {
			auth.AbortWithUnauthorized(c, err)
			return
		}

		userCode, role, err := authSvc.ParseAccessToken(token)
		if err != nil {
			log.Printf("token parse error: %v", err)
			auth.AbortWithUnauthorized(c, err)
			return
		}

		if role != auth.RoleAdmin {
			log.Printf("access denied: user %s has role %s, want admin", userCode, role)
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "forbidden_insufficient_permissions"})
			return
		}

		// 컨텍스트에 사용자 정보 저장
		c.Set("user_code", userCode)
		c.Set("role", role)

		c.Next()
	}
}
