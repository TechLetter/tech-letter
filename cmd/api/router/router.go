package router

import (
	"context"
	"net/http"

	"github.com/gin-gonic/gin"
	swaggerFiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"

	"tech-letter/cmd/api/handlers"
	"tech-letter/cmd/api/services"
	"tech-letter/db"
	_ "tech-letter/docs"
	"tech-letter/repositories"

	"go.mongodb.org/mongo-driver/bson"
)

func New() *gin.Engine {
	r := gin.Default()

	// Health check
	r.GET("/health", func(c *gin.Context) {
		// Try ping MongoDB
		if err := db.Database().RunCommand(context.Background(), bson.D{{Key: "ping", Value: 1}}).Err(); err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"status": "degraded", "mongo": "down", "error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	// Swagger
	r.GET("/swagger/*any", ginSwagger.WrapHandler(swaggerFiles.Handler))

	// v1 routes
	api := r.Group("/api/v1")
	{
		postsRepo := repositories.NewPostRepository(db.Database())
		postsSvc := services.NewPostService(postsRepo)
		api.GET("/posts", handlers.ListPostsHandler(postsSvc))
		api.GET("/posts/:id", handlers.GetPostHandler(postsSvc))
		api.POST("/posts/:id/view", handlers.IncrementPostViewCountHandler(postsSvc))

		blogsRepo := repositories.NewBlogRepository(db.Database())
		blogsSvc := services.NewBlogService(blogsRepo)
		api.GET("/blogs", handlers.ListBlogsHandler(blogsSvc))
	}

	return r
}
