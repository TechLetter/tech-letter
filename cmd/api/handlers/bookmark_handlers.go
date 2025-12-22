package handlers

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/clients/userclient"
	"tech-letter/cmd/api/dto"
	"tech-letter/cmd/api/services"
)

// AddBookmarkHandler godoc
// @Summary      포스트 북마크 추가
// @Description  현재 로그인한 사용자의 지정된 포스트를 북마크합니다.
// @Tags         posts
// @Security     BearerAuth
// @Param        id             path    string  true   "포스트 ObjectID"
// @Produce      json
// @Success      201  {object}  dto.MessageResponseDTO
// @Failure      400  {object}  dto.ErrorResponseDTO
// @Failure      401  {object}  dto.ErrorResponseDTO
// @Failure      500  {object}  dto.ErrorResponseDTO
// @Router       /posts/{id}/bookmark [post]
func AddBookmarkHandler(bookmarkSvc *services.BookmarkService, authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		postID := c.Param("id")
		if postID == "" {
			c.JSON(http.StatusBadRequest, dto.ErrorResponseDTO{Error: "missing_post_id"})
			return
		}

		if err := bookmarkSvc.AddBookmark(c.Request.Context(), userCode, postID); err != nil {
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: "failed_to_add_bookmark"})
			return
		}

		c.JSON(http.StatusCreated, dto.MessageResponseDTO{Message: "bookmark_created"})
	}
}

// RemoveBookmarkHandler godoc
// @Summary      포스트 북마크 제거
// @Description  현재 로그인한 사용자의 지정된 포스트 북마크를 해제합니다.
// @Tags         posts
// @Security     BearerAuth
// @Param        id             path    string  true   "포스트 ObjectID"
// @Produce      json
// @Success      204  {string}  string  "콘텐츠 없음"
// @Failure      400  {object}  dto.ErrorResponseDTO
// @Failure      401  {object}  dto.ErrorResponseDTO
// @Failure      404  {object}  dto.ErrorResponseDTO
// @Failure      500  {object}  dto.ErrorResponseDTO
// @Router       /posts/{id}/bookmark [delete]
func RemoveBookmarkHandler(bookmarkSvc *services.BookmarkService, authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		postID := c.Param("id")
		if postID == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "missing_post_id"})
			return
		}

		err := bookmarkSvc.RemoveBookmark(c.Request.Context(), userCode, postID)
		if err != nil {
			if err == userclient.ErrNotFound {
				c.JSON(http.StatusNotFound, gin.H{"error": "bookmark_not_found"})
				return
			}
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed_to_remove_bookmark"})
			return
		}

		c.Status(http.StatusNoContent)
	}
}

// ListBookmarkedPostsHandler godoc
// @Summary      북마크한 포스트 목록 조회
// @Description  현재 로그인한 사용자의 북마크한 포스트들을 /posts 목록과 동일한 형식으로 조회합니다.
// @Tags         posts
// @Security     BearerAuth
// @Param        page           query   int     false  "페이지 번호 (1부터 시작)"
// @Param        page_size      query   int     false  "페이지 크기 (최대 100)"
// @Produce      json
// @Success      200  {object}  dto.PaginationPostDTO
// @Failure      401  {object}  dto.ErrorResponseDTO
// @Failure      500  {object}  dto.ErrorResponseDTO
// @Router       /posts/bookmarks [get]
func ListBookmarkedPostsHandler(bookmarkSvc *services.BookmarkService, authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))

		result, err := bookmarkSvc.ListBookmarkedPosts(c.Request.Context(), userCode, page, pageSize)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed_to_list_bookmarks"})
			return
		}

		c.JSON(http.StatusOK, result)
	}
}
