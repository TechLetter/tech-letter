package handlers

import (
	"net/http"
	"strconv"

	_ "tech-letter/cmd/api/dto"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/services"
)

// ListPostsHandler godoc
// @Summary      List posts
// @Description  List summarized posts with filters and pagination
// @Tags         posts
// @Param        page          query  int     false  "Page number (1-based)"
// @Param        page_size     query  int     false  "Page size (<=100)"
// @Param        categories    query  []string  false  "Categories (OR match)"
// @Param        tags          query  []string  false  "Tags (OR match)"
// @Param        blog_id       query  string  false  "Blog ID"
// @Param        blog_name     query  string  false  "Blog name"
// @Produce      json
// @Success      200  {object}  dto.PaginationPostDTO
// @Router       /posts [get]
func ListPostsHandler(svc *services.PostService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var in services.ListPostsInput
		// pagination
		in.Page, _ = strconv.Atoi(c.DefaultQuery("page", "1"))
		in.PageSize, _ = strconv.Atoi(c.DefaultQuery("page_size", "20"))
		// filters
		in.Categories = c.QueryArray("categories")
		in.Tags = c.QueryArray("tags")
		in.BlogID = c.Query("blog_id")
		in.BlogName = c.Query("blog_name")

		page, err := svc.List(c.Request.Context(), in)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, page)
	}
}

// GetPostHandler godoc
// @Summary      Get post by id
// @Description  Get a single post by ObjectID
// @Tags         posts
// @Param        id   path   string  true  "ObjectID"
// @Produce      json
// @Success      200  {object}  dto.PostDTO
// @Router       /posts/{id} [get]
func GetPostHandler(svc *services.PostService) gin.HandlerFunc {
	return func(c *gin.Context) {
		idStr := c.Param("id")
		post, err := svc.GetByID(c.Request.Context(), idStr)
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
			return
		}
		c.JSON(http.StatusOK, post)
	}
}

// IncrementPostViewCountHandler godoc
// @Summary      Increment post view count
// @Description  Increment the view_count of a post by 1
// @Tags         posts
// @Param        id   path   string  true  "ObjectID"
// @Produce      json
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Router       /posts/{id}/view [post]
func IncrementPostViewCountHandler(svc *services.PostService) gin.HandlerFunc {
	return func(c *gin.Context) {
		idStr := c.Param("id")
		err := svc.IncrementViewCount(c.Request.Context(), idStr)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid post id or post not found"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "view count incremented successfully"})
	}
}

// ListBlogsHandler godoc
// @Summary      List blogs
// @Description  List blogs with simple pagination
// @Tags         blogs
// @Param        page          query  int     false  "Page number (1-based)"
// @Param        page_size     query  int     false  "Page size (<=100)"
// @Produce      json
// @Success      200  {object}  dto.PaginationBlogDTO
// @Router       /blogs [get]
func ListBlogsHandler(svc *services.BlogService) gin.HandlerFunc {
	return func(c *gin.Context) {
		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
		resp, err := svc.List(c.Request.Context(), services.ListBlogsInput{Page: page, PageSize: pageSize})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}
