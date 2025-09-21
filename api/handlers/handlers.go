package handlers

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/bson/primitive"

	"tech-letter/repositories"
)

// ListPostsHandler godoc
// @Summary      List posts
// @Description  List summarized posts with filters and pagination
// @Tags         posts
// @Param        page          query  int     false  "Page number (1-based)"
// @Param        page_size     query  int     false  "Page size (<=100)"
// @Param        category      query  string  false  "Category filter"
// @Param        tag           query  string  false  "Tag filter"
// @Param        q             query  string  false  "Keyword search (title/summary/blog)"
// @Param        html_fetched  query  bool    false  "Filter by html_fetched status"
// @Param        text_parsed   query  bool    false  "Filter by text_parsed status"
// @Param        ai_summarized query  bool    false  "Filter by ai_summarized status"
// @Produce      json
// @Success      200  {array}  models.Post
// @Router       /posts [get]
func ListPostsHandler(repo *repositories.PostRepository) gin.HandlerFunc {
	return func(c *gin.Context) {
		var opt repositories.ListPostsOptions
		// pagination
		opt.Page, _ = strconv.Atoi(c.DefaultQuery("page", "1"))
		opt.PageSize, _ = strconv.Atoi(c.DefaultQuery("page_size", "20"))
		// filters
		opt.Category = c.Query("category")
		opt.Tag = c.Query("tag")
		opt.Q = c.Query("q")
		if v := c.Query("html_fetched"); v != "" {
			b, _ := strconv.ParseBool(v)
			opt.HTMLFetched = &b
		}
		if v := c.Query("text_parsed"); v != "" {
			b, _ := strconv.ParseBool(v)
			opt.TextParsed = &b
		}
		if v := c.Query("ai_summarized"); v != "" {
			b, _ := strconv.ParseBool(v)
			opt.AISummarized = &b
		}

		items, err := repo.List(c.Request.Context(), opt)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, items)
	}
}

// GetPostHandler godoc
// @Summary      Get post by id
// @Description  Get a single post by ObjectID
// @Tags         posts
// @Param        id   path   string  true  "ObjectID"
// @Produce      json
// @Success      200  {object}  models.Post
// @Router       /posts/{id} [get]
func GetPostHandler(repo *repositories.PostRepository) gin.HandlerFunc {
	return func(c *gin.Context) {
		idStr := c.Param("id")
		id, err := primitive.ObjectIDFromHex(idStr)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid id"})
			return
		}
		post, err := repo.FindByID(c.Request.Context(), id)
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
			return
		}
		c.JSON(http.StatusOK, post)
	}
}
