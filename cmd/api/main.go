package main

import (
	"context"
	"log"
	"net/http"

	_ "tech-letter/docs" // swag will generate this package
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/api/router"
)

// @title           Tech-Letter API
// @version         1.0
// @description     API for browsing summarized tech blog posts
// @BasePath        /api/v1
func main() {
	config.InitApp()
	if err := db.Init(context.Background()); err != nil {
		log.Fatal(err)
	}
	r := router.New()

	if err := r.Run(":8080"); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
