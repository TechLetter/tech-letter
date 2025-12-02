package main

import (
	"log"
	"net/http"

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

	handler := cors.New(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"*"},
		AllowCredentials: true,
	}).Handler(r)

	if err := http.ListenAndServe(":8080", handler); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
