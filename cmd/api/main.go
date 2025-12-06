package main

import (
	"log"
	"net/http"
	"os"
	"strings"

	"tech-letter/cmd/api/router"
	"tech-letter/cmd/internal/logger"
	_ "tech-letter/docs" // swag will generate this package

	"github.com/rs/cors"
)

// @title           Tech-Letter API
// @version         1.0
// @description     API for browsing summarized tech blog posts
// @BasePath        /api/v1

func main() {
	// API 서버 로그 레벨은 환경변수 LOG_LEVEL 로 제어한다.
	logger.InitFromEnv("LOG_LEVEL")

	r := router.New()

	// 프론트 스펙: Authorization 헤더 기반, 쿠키/withCredentials 사용 안 함.
	// CORS_ALLOWED_ORIGINS 환경변수로 허용 Origin 을 제어한다.
	allowedOriginsEnv := os.Getenv("CORS_ALLOWED_ORIGINS")
	var allowedOrigins []string
	if allowedOriginsEnv == "" {
		// 기본값: 개발 편의를 위해 전체 허용 (단, 쿠키는 사용하지 않음)
		allowedOrigins = []string{"*"}
	} else {
		for _, o := range strings.Split(allowedOriginsEnv, ",") {
			if trimmed := strings.TrimSpace(o); trimmed != "" {
				allowedOrigins = append(allowedOrigins, trimmed)
			}
		}
	}

	corsOpts := cors.Options{
		AllowedOrigins:   allowedOrigins,
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Authorization", "Content-Type"},
		AllowCredentials: false,
	}

	handler := cors.New(corsOpts).Handler(r)

	if err := http.ListenAndServe(":8080", handler); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
