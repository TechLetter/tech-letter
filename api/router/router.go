package router

import (
    "context"
    "net/http"
	"github.com/gin-gonic/gin"
    ginSwagger "github.com/swaggo/gin-swagger"
    swaggerFiles "github.com/swaggo/files"

    _ "tech-letter/docs"
    "tech-letter/db"
    "tech-letter/api/handlers"
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
        api.GET("/posts", handlers.ListPostsHandler(postsRepo))
        api.GET("/posts/:id", handlers.GetPostHandler(postsRepo))
    }

    return r
}
