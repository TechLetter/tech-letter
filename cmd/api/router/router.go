package router

import (
	"context"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	swaggerFiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"

	"tech-letter/cmd/api/contentclient"
	"tech-letter/cmd/api/handlers"
	"tech-letter/cmd/api/services"
	_ "tech-letter/docs"
)

func New() *gin.Engine {
	r := gin.Default()

	// Health check
	r.GET("/health", func(c *gin.Context) {
		client := contentclient.New()
		ctx, cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
		defer cancel()
		if err := client.Health(ctx); err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"status": "degraded", "content_service": "down", "error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	// Swagger
	r.GET("/swagger/*any", ginSwagger.WrapHandler(swaggerFiles.Handler))

	// v1 routes
	api := r.Group("/api/v1")
	{
		contentClient := contentclient.New()
		postsSvc := services.NewPostService(contentClient)
		api.GET("/posts", handlers.ListPostsHandler(postsSvc))
		api.GET("/posts/:id", handlers.GetPostHandler(postsSvc))
		api.POST("/posts/:id/view", handlers.IncrementPostViewCountHandler(postsSvc))

		blogsSvc := services.NewBlogService(contentClient)
		api.GET("/blogs", handlers.ListBlogsHandler(blogsSvc))
	}

	return r
}
