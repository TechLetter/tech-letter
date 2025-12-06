package middleware

import (
	"bytes"
	"io"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/trace"
	"tech-letter/cmd/internal/logger"
)

const (
	headerRequestID = "X-Request-Id"
	headerSpanID    = "X-Span-Id"
)

// RequestTrace는 모든 inbound HTTP 요청에 대해 Request ID와 Span ID를 보장하고,
// 이를 컨텍스트/헤더에 저장한 뒤 Gateway 로그에 포함시킨다.
func RequestTrace() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		req := c.Request

		requestID := req.Header.Get(headerRequestID)
		if requestID == "" {
			requestID = trace.GenerateID()
		}

		// span 시퀀스를 0으로 초기화한다. (inbound 로그는 span_id=0,
		// 마이크로서비스 호출은 1,2,3,... 로 증가)
		ctxWithTrace := trace.WithRequestAndSpan(req.Context(), requestID, 0)
		c.Request = req.WithContext(ctxWithTrace)
		req = c.Request

		// 헤더에 세팅: 마이크로서비스 및 응답 헤더에서 동일 ID를 사용할 수 있도록 한다.
		currentSpan := trace.CurrentSpanID(ctxWithTrace) // 보통 "0"
		c.Request.Header.Set(headerRequestID, requestID)
		c.Request.Header.Set(headerSpanID, currentSpan)
		c.Writer.Header().Set(headerRequestID, requestID)
		c.Writer.Header().Set(headerSpanID, currentSpan)

		// 쿼리 및 요청 바디 스니펫을 함께 로깅한다.
		// query_params 는 멀티 값 쿼리도 모두 보존하기 위해 map[string][]string 으로 기록한다.
		queryParams := map[string][]string{}
		for key, values := range req.URL.Query() {
			if len(values) > 0 {
				queryParams[key] = values
			}
		}
		var bodySnippet string
		if req.Body != nil && req.ContentLength != 0 &&
			(req.Method == http.MethodPost || req.Method == http.MethodPut || req.Method == http.MethodPatch || req.Method == http.MethodDelete) {
			if bodyBytes, err := io.ReadAll(req.Body); err == nil {
				if len(bodyBytes) > 0 {
					const maxBodyLog = 1024
					if len(bodyBytes) > maxBodyLog {
						bodySnippet = string(bodyBytes[:maxBodyLog])
					} else {
						bodySnippet = string(bodyBytes)
					}
				}
				// gin 핸들러에서 다시 읽을 수 있도록 Body 를 복원한다.
				c.Request.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
			}
		}

		c.Next()

		status := c.Writer.Status()
		finalSpan := trace.CurrentSpanID(c.Request.Context())
		duration := time.Since(start)
		fields := logger.Fields{
			"method":       req.Method,
			"path":         req.URL.Path,
			"query_params": queryParams,
			"status":       status,
			"duration":     duration.String(),
			"request_id":   requestID,
			"span_id":      finalSpan,
		}
		if bodySnippet != "" {
			fields["body"] = bodySnippet
		}
		logger.InfoWithFields("completed request", fields)
	}
}
