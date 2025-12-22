package handlers

import (
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/dto"
	"tech-letter/cmd/api/services"
)

// GetUserProfileHandler godoc
// @Summary      현재 로그인한 사용자 프로필 조회
// @Description  Authorization 헤더에 포함된 JWT를 검증하고, 현재 로그인한 사용자의 프로필 정보를 조회합니다.
// @Tags         users
// @Security     BearerAuth
// @Produce      json
// @Success      200  {object}  dto.UserProfileDTO
// @Failure      401  {object}  dto.ErrorResponseDTO
// @Failure      404  {object}  dto.ErrorResponseDTO
// @Failure      500  {object}  dto.ErrorResponseDTO
// @Router       /users/profile [get]
func GetUserProfileHandler(authSvc *services.AuthService, userSvc *services.UserService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		profile, err := userSvc.GetUserProfile(c.Request.Context(), userCode)
		if err != nil {
			if errors.Is(err, services.ErrUserNotFound) {
				c.JSON(http.StatusNotFound, dto.ErrorResponseDTO{Error: "user_not_found"})
				return
			}
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: "failed_to_load_profile"})
			return
		}

		// 크레딧 잔액 조회
		credits, err := userSvc.GetCredits(c.Request.Context(), userCode)
		creditRemaining := 0
		if err == nil {
			creditRemaining = credits.TotalRemaining
		}

		c.JSON(http.StatusOK, dto.UserProfileDTO{
			UserCode:     profile.UserCode,
			Provider:     profile.Provider,
			ProviderSub:  profile.ProviderSub,
			Email:        profile.Email,
			Name:         profile.Name,
			ProfileImage: profile.ProfileImage,
			Role:         profile.Role,
			CreatedAt:    profile.CreatedAt.Format(time.RFC3339),
			UpdatedAt:    profile.UpdatedAt.Format(time.RFC3339),
			Credits:      creditRemaining,
		})
	}
}

// DeleteCurrentUserHandler godoc
// @Summary      회원 탈퇴 (현재 로그인한 사용자)
// @Description  Authorization 헤더의 JWT에서 user_code를 추출해 해당 사용자의 계정과 북마크를 삭제합니다.
// @Tags         users
// @Security     BearerAuth
// @Produce      json
// @Success      200  {object}  dto.MessageResponseDTO
// @Failure      401  {object}  dto.ErrorResponseDTO
// @Failure      404  {object}  dto.ErrorResponseDTO
// @Failure      500  {object}  dto.ErrorResponseDTO
// @Router       /users/me [delete]
func DeleteCurrentUserHandler(authSvc *services.AuthService, userSvc *services.UserService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		if err := userSvc.DeleteUser(c.Request.Context(), userCode); err != nil {
			if errors.Is(err, services.ErrUserNotFound) {
				c.JSON(http.StatusNotFound, dto.ErrorResponseDTO{Error: "user_not_found"})
				return
			}
			c.JSON(http.StatusInternalServerError, dto.ErrorResponseDTO{Error: "failed_to_delete_user"})
			return
		}

		c.JSON(http.StatusOK, dto.MessageResponseDTO{Message: "user_deleted"})
	}
}
