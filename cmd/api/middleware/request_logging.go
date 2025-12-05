package middleware

import (
	"time"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/internal/logger"
)

// RequestLoggingMiddleware 는 API Gateway 진입부터 응답까지 걸린 시간을 로깅한다.
func RequestLoggingMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()

		path := c.Request.URL.Path
		method := c.Request.Method

		c.Next()

		status := c.Writer.Status()
		durationMillis := time.Since(start).Milliseconds()

		logger.Log.Infof(
			"api_request method=%s path=%s status=%d duration_ms=%d",
			method,
			path,
			status,
			durationMillis,
		)
	}
}
