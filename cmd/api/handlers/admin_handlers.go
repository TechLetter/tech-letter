package handlers

import (
	"net/http"
	"strconv"

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
// @Success 200 {object} object
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
// @Description List all users with pagination
// @Tags admin
// @Accept json
// @Produce json
// @Param page query int false "Page number" default(1)
// @Param page_size query int false "Page size" default(20)
// @Success 200 {object} object
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
// @Success 200 {object} object
// @Failure 500 {object} dto.ErrorResponseDTO
// @Router /api/v1/admin/blogs [get]
func AdminListBlogsHandler(svc *services.BlogService) gin.HandlerFunc {
	return func(c *gin.Context) {
		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))

		resp, err := svc.List(c.Request.Context(), services.ListBlogsInput{
			Page:     page,
			PageSize: pageSize,
		})
		if err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}
