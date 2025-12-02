package main

import (
	"log"
	"net/http"

	"tech-letter/cmd/api/router"
	"tech-letter/config"
	_ "tech-letter/docs" // swag will generate this package

	"github.com/rs/cors"
)

// @title           Tech-Letter API
// @version         1.0
// @description     API for browsing summarized tech blog posts
// @BasePath        /api/v1

func main() {
	config.InitApp()
	cfg := config.GetConfig()
	config.InitLogger(cfg.API.Logging)

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
