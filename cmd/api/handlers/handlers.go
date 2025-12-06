package handlers

import (
	"net/http"
	"strconv"

	_ "tech-letter/cmd/api/dto"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/services"
)

// ListPostsHandler godoc
// @Summary      포스트 목록 조회
// @Description  필터와 페이징 조건으로 요약된 기술 블로그 포스트 목록을 조회합니다.
// @Tags         posts
// @Param        page                  query  int       false  "페이지 번호 (1부터 시작)"
// @Param        page_size             query  int       false  "페이지 크기 (최대 100)"
// @Param        categories            query  []string  false  "카테고리 목록 (OR 조건)"
// @Param        tags                  query  []string  false  "태그 목록 (OR 조건)"
// @Param        blog_id               query  string    false  "블로그 ID"
// @Param        blog_name             query  string    false  "블로그 이름"
// @Param        status_ai_summarized  query  bool      false  "AI 요약 완료 여부"
// @Produce      json
// @Success      200  {object}  dto.PaginationPostDTO
// @Router       /posts [get]
func ListPostsHandler(postSvc *services.PostService, bookmarkSvc *services.BookmarkService, authSvc *services.AuthService) gin.HandlerFunc {
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
		// status filters
		if statusStr := c.Query("status_ai_summarized"); statusStr != "" {
			if val, err := strconv.ParseBool(statusStr); err == nil {
				in.StatusAISummarized = &val
			}
		}

		page, err := postSvc.List(c.Request.Context(), in)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		userCode, hasToken, ok := optionalUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}
		if hasToken {
			marked, err := bookmarkSvc.MarkBookmarked(c.Request.Context(), userCode, page.Data)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "failed_to_load_bookmarks"})
				return
			}
			page.Data = marked
		}

		c.JSON(http.StatusOK, page)
	}
}

// GetPostHandler godoc
// @Summary      포스트 단건 조회
// @Description  ObjectID 기준으로 특정 포스트를 조회합니다.
// @Tags         posts
// @Param        id   path   string  true  "포스트 ObjectID"
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
// @Summary      포스트 조회 수 증가
// @Description  지정한 포스트의 조회 수(view_count)를 1 증가시킵니다.
// @Tags         posts
// @Param        id   path   string  true  "포스트 ObjectID"
// @Produce      json
// @Success      200  {object}  dto.MessageResponseDTO
// @Failure      400  {object}  dto.ErrorResponseDTO
// @Failure      404  {object}  dto.ErrorResponseDTO
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
// @Summary      블로그 목록 조회
// @Description  단순 페이징으로 블로그 목록을 조회합니다.
// @Tags         blogs
// @Param        page          query  int     false  "페이지 번호 (1부터 시작)"
// @Param        page_size     query  int     false  "페이지 크기 (최대 100)"
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

// GetCategoryFiltersHandler godoc
// @Summary      카테고리 필터 조회
// @Description  포스트 개수와 함께 카테고리 필터 목록을 조회합니다.
// @Tags         filters
// @Param        blog_id  query  string    false  "블로그 ID"
// @Param        tags     query  []string  false  "태그 목록 (OR 조건)"
// @Produce      json
// @Success      200  {object}  dto.CategoryFilterDTO
// @Router       /filters/categories [get]
func GetCategoryFiltersHandler(svc *services.FilterService) gin.HandlerFunc {
	return func(c *gin.Context) {
		blogID := c.Query("blog_id")
		tags := c.QueryArray("tags")

		resp, err := svc.GetCategoryFilters(c.Request.Context(), blogID, tags)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// GetTagFiltersHandler godoc
// @Summary      태그 필터 조회
// @Description  포스트 개수와 함께 태그 필터 목록을 조회합니다.
// @Tags         filters
// @Param        blog_id     query  string    false  "블로그 ID"
// @Param        categories  query  []string  false  "카테고리 목록 (OR 조건)"
// @Produce      json
// @Success      200  {object}  dto.TagFilterDTO
// @Router       /filters/tags [get]
func GetTagFiltersHandler(svc *services.FilterService) gin.HandlerFunc {
	return func(c *gin.Context) {
		blogID := c.Query("blog_id")
		categories := c.QueryArray("categories")

		resp, err := svc.GetTagFilters(c.Request.Context(), blogID, categories)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

// GetBlogFiltersHandler godoc
// @Summary      블로그 필터 조회
// @Description  포스트 개수와 함께 블로그 필터 목록을 조회합니다.
// @Tags         filters
// @Param        categories  query  []string  false  "카테고리 목록 (OR 조건)"
// @Param        tags        query  []string  false  "태그 목록 (OR 조건)"
// @Produce      json
// @Success      200  {object}  dto.BlogFilterDTO
// @Router       /filters/blogs [get]
func GetBlogFiltersHandler(svc *services.FilterService) gin.HandlerFunc {
	return func(c *gin.Context) {
		categories := c.QueryArray("categories")
		tags := c.QueryArray("tags")

		resp, err := svc.GetBlogFilters(c.Request.Context(), categories, tags)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}
