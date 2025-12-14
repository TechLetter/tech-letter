package router

import (
	"context"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	swaggerFiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"

	"tech-letter/cmd/api/clients/chatbotclient"
	"tech-letter/cmd/api/clients/contentclient"
	"tech-letter/cmd/api/clients/userclient"
	"tech-letter/cmd/api/handlers"
	"tech-letter/cmd/api/middleware"
	"tech-letter/cmd/api/services"
	_ "tech-letter/docs"
)

func New() *gin.Engine {
	r := gin.Default()
	r.Use(middleware.RequestTrace())

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
	authSvc, err := services.NewAuthServiceFromEnv()
	if err != nil {
		panic(err)
	}

	api := r.Group("/api/v1")
	{
		chatbotClient := chatbotclient.New()
		contentClient := contentclient.New()
		userClient := userclient.New()
		postsSvc := services.NewPostService(contentClient)
		bookmarkSvc := services.NewBookmarkService(contentClient, userClient)
		chatbotSvc := services.NewChatbotService(chatbotClient)
		adminSvc := services.NewAdminService(contentClient, userClient)

		api.GET("/posts", handlers.ListPostsHandler(postsSvc, bookmarkSvc, authSvc))
		api.GET("/posts/:id", handlers.GetPostHandler(postsSvc))
		api.POST("/posts/:id/view", handlers.IncrementPostViewCountHandler(postsSvc))
		api.POST("/posts/:id/bookmark", handlers.AddBookmarkHandler(bookmarkSvc, authSvc))
		api.DELETE("/posts/:id/bookmark", handlers.RemoveBookmarkHandler(bookmarkSvc, authSvc))
		api.GET("/posts/bookmarks", handlers.ListBookmarkedPostsHandler(bookmarkSvc, authSvc))

		blogsSvc := services.NewBlogService(contentClient)
		api.GET("/blogs", handlers.ListBlogsHandler(blogsSvc))

		filtersSvc := services.NewFilterService(contentClient)
		api.GET("/filters/categories", handlers.GetCategoryFiltersHandler(filtersSvc))
		api.GET("/filters/tags", handlers.GetTagFiltersHandler(filtersSvc))
		api.GET("/filters/blogs", handlers.GetBlogFiltersHandler(filtersSvc))

		api.GET("/auth/google/login", handlers.GoogleLoginHandler(authSvc))
		api.GET("/auth/google/callback", handlers.GoogleCallbackHandler(authSvc))
		api.POST("/auth/session/exchange", handlers.SessionExchangeHandler(authSvc))
		api.GET("/users/profile", handlers.GetUserProfileHandler(authSvc))
		api.DELETE("/users/me", handlers.DeleteCurrentUserHandler(authSvc))

		api.POST("/chatbot/chat", handlers.ChatbotChatHandler(chatbotSvc, authSvc))

		// Admin Routes
		admin := api.Group("/admin")
		admin.Use(middleware.AdminAuthMiddleware(authSvc))
		{
			// TODO: Implement Admin Handlers
			admin.GET("/blogs", handlers.AdminListBlogsHandler(blogsSvc))
			admin.GET("/posts", handlers.AdminListPostsHandler(adminSvc))
			admin.POST("/posts", handlers.AdminCreatePostHandler(adminSvc))
			admin.DELETE("/posts/:id", handlers.AdminDeletePostHandler(adminSvc))
			admin.POST("/posts/:id/summarize", handlers.AdminTriggerSummaryHandler(adminSvc))
			admin.POST("/posts/:id/embed", handlers.AdminTriggerEmbeddingHandler(adminSvc))
			admin.GET("/users", handlers.AdminListUsersHandler(adminSvc))
		}
	}

	return r
}
