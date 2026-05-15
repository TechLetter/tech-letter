package handlers

import (
	"net/http"
	"strconv"

	"tech-letter/cmd/api/clients/contentclient"
	"tech-letter/cmd/api/clients/userclient"
	"tech-letter/cmd/api/dto"
	"tech-letter/cmd/api/services"

	"github.com/gin-gonic/gin"
)

// @Summary List posts for admin
// @Description List all posts with pagination and optional status/blog filtering
// @Tags admin
// @Accept json
// @Produce json
// @Param page query int false "Page number" default(1)
// @Param page_size query int false "Page size" default(20)
// @Param blog_id query string false "Filter by blog ID"
// @Param status_ai_summarized query bool false "Filter by AI summary status"
// @Param status_embedded query bool false "Filter by embedding status"
// @Success 200 {object} dto.PaginationAdminPostDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/posts [get]
func AdminListPostsHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
		blogID := c.Query("blog_id")

		var statusAISummarized *bool
		if v := c.Query("status_ai_summarized"); v != "" {
			if b, err := strconv.ParseBool(v); err == nil {
				statusAISummarized = &b
			}
		}

		var statusEmbedded *bool
		if v := c.Query("status_embedded"); v != "" {
			if b, err := strconv.ParseBool(v); err == nil {
				statusEmbedded = &b
			}
		}

		// Admin wants to see all posts, no filtering by default
		resp, err := svc.ListPosts(c.Request.Context(), services.AdminListPostsInput{
			Page:               page,
			PageSize:           pageSize,
			BlogID:             blogID,
			StatusAISummarized: statusAISummarized,
			StatusEmbedded:     statusEmbedded,
		})
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// @Summary Create a post manually
// @Description Create a new post and trigger AI summary
// @Tags admin
// @Accept json
// @Produce json
// @Param body body object true "Post creation request"
// @Success 200 {object} dto.CreatePostResponseDTO
// @Failure 400 {object} dto.ErrorResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/posts [post]
func AdminCreatePostHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req struct {
			Title  string `json:"title" binding:"required"`
			Link   string `json:"link" binding:"required"`
			BlogID string `json:"blog_id" binding:"required"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}

		out, err := svc.CreatePost(c.Request.Context(), req.Title, req.Link, req.BlogID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, out)
	}
}

// @Summary Delete a post
// @Description Delete a post by ID
// @Tags admin
// @Produce json
// @Param id path string true "Post ID"
// @Success 200 {object} dto.MessageResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/posts/{id} [delete]
func AdminDeletePostHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		if err := svc.DeletePost(c.Request.Context(), id); err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, dto.MessageResponseDTO{Message: "post deleted successfully"})
	}
}

// @Summary Trigger AI summary
// @Description Manually trigger AI summary for a post
// @Tags admin
// @Produce json
// @Param id path string true "Post ID"
// @Success 200 {object} dto.MessageResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/posts/{id}/summarize [post]
func AdminTriggerSummaryHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		if err := svc.TriggerSummary(c.Request.Context(), id); err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, dto.MessageResponseDTO{Message: "summary triggered successfully"})
	}
}

// @Summary Trigger embedding
// @Description Manually trigger vector embedding for a post
// @Tags admin
// @Produce json
// @Param id path string true "Post ID"
// @Success 200 {object} dto.MessageResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/posts/{id}/embed [post]
func AdminTriggerEmbeddingHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		if err := svc.TriggerEmbedding(c.Request.Context(), id); err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, dto.MessageResponseDTO{Message: "embedding triggered successfully"})
	}
}

// @Summary List users for admin
// @Description List all users with pagination and credit information
// @Tags admin
// @Accept json
// @Produce json
// @Param page query int false "Page number" default(1)
// @Param page_size query int false "Page size" default(20)
// @Success 200 {object} dto.PaginationAdminUserDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/users [get]
func AdminListUsersHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))

		resp, err := svc.ListUsers(c.Request.Context(), page, pageSize)
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// @Summary List blogs for admin
// @Description List all blogs with pagination
// @Tags admin
// @Accept json
// @Produce json
// @Param page query int false "Page number" default(1)
// @Param page_size query int false "Page size" default(20)
// @Success 200 {object} dto.PaginationBlogDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/blogs [get]
func AdminListBlogsHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))

		resp, err := svc.ListBlogs(c.Request.Context(), page, pageSize)
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// @Summary Create blog for admin
// @Description Create a blog source used by RSS collection
// @Tags admin
// @Accept json
// @Produce json
// @Param body body dto.BlogMutationRequestDTO true "Blog create request"
// @Success 201 {object} dto.AdminBlogDTO
// @Failure 400 {object} dto.ErrorResponseDTO
// @Failure 409 {object} dto.ErrorResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/blogs [post]
func AdminCreateBlogHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req dto.BlogMutationRequestDTO
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}

		resp, err := svc.CreateBlog(c.Request.Context(), req)
		if err != nil {
			writeAdminContentError(c, err)
			return
		}
		c.JSON(http.StatusCreated, resp)
	}
}

// @Summary Update blog for admin
// @Description Update a blog source used by RSS collection
// @Tags admin
// @Accept json
// @Produce json
// @Param id path string true "Blog ID"
// @Param body body dto.BlogMutationRequestDTO true "Blog update request"
// @Success 200 {object} dto.AdminBlogDTO
// @Failure 400 {object} dto.ErrorResponseDTO
// @Failure 404 {object} dto.ErrorResponseDTO
// @Failure 409 {object} dto.ErrorResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/blogs/{id} [put]
func AdminUpdateBlogHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req dto.BlogMutationRequestDTO
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}

		resp, err := svc.UpdateBlog(c.Request.Context(), c.Param("id"), req)
		if err != nil {
			writeAdminContentError(c, err)
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// @Summary Delete blog for admin
// @Description Delete a blog source and optionally delete all posts under that blog
// @Tags admin
// @Produce json
// @Param id path string true "Blog ID"
// @Param delete_posts query bool false "Delete all posts for this blog"
// @Success 200 {object} dto.DeleteBlogResponseDTO
// @Failure 404 {object} dto.ErrorResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/blogs/{id} [delete]
func AdminDeleteBlogHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		deletePosts, _ := strconv.ParseBool(c.DefaultQuery("delete_posts", "false"))

		resp, err := svc.DeleteBlog(c.Request.Context(), c.Param("id"), deletePosts)
		if err != nil {
			writeAdminContentError(c, err)
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

func writeAdminContentError(c *gin.Context, err error) {
	switch {
	case contentclient.IsStatus(err, http.StatusBadRequest):
		c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: err.Error()})
	case contentclient.IsStatus(err, http.StatusNotFound):
		c.JSON(http.StatusNotFound, dto.ErrorResponseDTO{Error: err.Error()})
	case contentclient.IsStatus(err, http.StatusConflict):
		c.JSON(http.StatusConflict, dto.ErrorResponseDTO{Error: err.Error()})
	default:
		c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
	}
}

// @Summary Grant credits to a user
// @Description Manually grant credits to a specific user (admin only)
// @Tags admin
// @Accept json
// @Produce json
// @Param user_code path string true "User Code"
// @Param body body dto.GrantCreditRequestDTO true "Credit grant request"
// @Success 200 {object} dto.GrantCreditResponseDTO
// @Failure 400 {object} dto.ErrorResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/users/{user_code}/credits [post]
func AdminGrantCreditHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode := c.Param("user_code")
		var req dto.GrantCreditRequestDTO
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}

		resp, err := svc.GrantCredit(c.Request.Context(), userCode, &req)
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// @Summary List chatbot suggested questions for admin
// @Description List all chatbot suggested questions including inactive ones
// @Tags admin
// @Produce json
// @Success 200 {array} dto.ChatbotSuggestedQuestionDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/chatbot/suggested-questions [get]
func AdminListChatbotSuggestedQuestionsHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		resp, err := svc.ListSuggestedQuestions(c.Request.Context())
		if err != nil {
			writeAdminUserError(c, err)
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// @Summary Create chatbot suggested question
// @Description Create a chatbot suggested question
// @Tags admin
// @Accept json
// @Produce json
// @Param body body dto.ChatbotSuggestedQuestionMutationDTO true "Suggested question"
// @Success 201 {object} dto.ChatbotSuggestedQuestionDTO
// @Failure 400 {object} dto.ErrorResponseDTO
// @Failure 409 {object} dto.ErrorResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/chatbot/suggested-questions [post]
func AdminCreateChatbotSuggestedQuestionHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req dto.ChatbotSuggestedQuestionMutationDTO
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		resp, err := svc.CreateSuggestedQuestion(c.Request.Context(), req)
		if err != nil {
			writeAdminUserError(c, err)
			return
		}
		c.JSON(http.StatusCreated, resp)
	}
}

// @Summary Update chatbot suggested question
// @Description Update a chatbot suggested question
// @Tags admin
// @Accept json
// @Produce json
// @Param id path string true "Suggested question ID"
// @Param body body dto.ChatbotSuggestedQuestionMutationDTO true "Suggested question"
// @Success 200 {object} dto.ChatbotSuggestedQuestionDTO
// @Failure 400 {object} dto.ErrorResponseDTO
// @Failure 404 {object} dto.ErrorResponseDTO
// @Failure 409 {object} dto.ErrorResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/chatbot/suggested-questions/{id} [put]
func AdminUpdateChatbotSuggestedQuestionHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req dto.ChatbotSuggestedQuestionMutationDTO
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		resp, err := svc.UpdateSuggestedQuestion(c.Request.Context(), c.Param("id"), req)
		if err != nil {
			writeAdminUserError(c, err)
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// @Summary Delete chatbot suggested question
// @Description Delete a chatbot suggested question
// @Tags admin
// @Produce json
// @Param id path string true "Suggested question ID"
// @Success 200 {object} dto.MessageResponseDTO
// @Failure 404 {object} dto.ErrorResponseDTO
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/chatbot/suggested-questions/{id} [delete]
func AdminDeleteChatbotSuggestedQuestionHandler(svc *services.AdminService) gin.HandlerFunc {
	return func(c *gin.Context) {
		if err := svc.DeleteSuggestedQuestion(c.Request.Context(), c.Param("id")); err != nil {
			writeAdminUserError(c, err)
			return
		}
		c.JSON(http.StatusOK, dto.MessageResponseDTO{Message: "suggested question deleted successfully"})
	}
}

func writeAdminUserError(c *gin.Context, err error) {
	switch {
	case userclient.IsStatus(err, http.StatusBadRequest):
		c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: err.Error()})
	case userclient.IsStatus(err, http.StatusNotFound):
		c.JSON(http.StatusNotFound, dto.ErrorResponseDTO{Error: err.Error()})
	case userclient.IsStatus(err, http.StatusConflict):
		c.JSON(http.StatusConflict, dto.ErrorResponseDTO{Error: err.Error()})
	default:
		c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
	}
}
