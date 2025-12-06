package handlers

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/services"
	"tech-letter/cmd/internal/logger"
)

const oauthStateCookieName = "oauth_state"

func generateState() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

// GoogleLoginHandler godoc
// @Summary      Google 로그인 시작
// @Description  state 값을 생성해 쿠키에 저장한 뒤, Google OAuth 인증 페이지로 리다이렉트합니다. 실패 시에도 프론트의 로그인 완료 페이지로 토큰 없이 이동합니다.
// @Tags         auth
// @Produce      json
// @Success      302  {string}  string  "Google OAuth 로그인 페이지 또는 로그인 완료 페이지로 리다이렉트"
// @Router       /auth/google/login [get]
func GoogleLoginHandler(authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		state, err := generateState()
		if err != nil {
			redirectURL := authSvc.GetRedirectURL()
			logger.ErrorWithFields("google login failed to generate state", logger.Fields{
				"error":       err.Error(),
				"redirect_to": redirectURL,
				"request_id":  c.Request.Header.Get("X-Request-Id"),
				"span_id":     c.Request.Header.Get("X-Span-Id"),
			})
			// 프론트 스펙: 실패 시에도 /login/success 로 토큰 없이 리다이렉트
			c.Redirect(http.StatusFound, redirectURL)
			return
		}

		// state 를 쿠키에 저장해 CSRF 를 방지한다.
		c.SetCookie(oauthStateCookieName, state, 300, "/", "", false, true)

		loginURL := authSvc.BuildGoogleLoginURL(state)
		logger.InfoWithFields("redirect to google oauth", logger.Fields{
			"redirect_to": loginURL,
			"request_id":  c.Request.Header.Get("X-Request-Id"),
			"span_id":     c.Request.Header.Get("X-Span-Id"),
		})
		c.Redirect(http.StatusFound, loginURL)
	}
}

// GoogleCallbackHandler godoc
// @Summary      Google OAuth 콜백 처리
// @Description  state 값을 검증하고, code로 Google 액세스 토큰을 교환한 뒤 사용자 정보를 조회/업서트하고 JWT를 발급하여 로그인 완료 페이지로 리다이렉트합니다.
// @Tags         auth
// @Produce      json
// @Success      302  {string}  string  "로그인 완료 페이지로 리다이렉트 (성공 시 토큰 포함)"
// @Router       /auth/google/callback [get]
func GoogleCallbackHandler(authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		state := c.Query("state")
		code := c.Query("code")
		redirectURL := authSvc.GetRedirectURL()

		if state == "" || code == "" {
			logger.ErrorWithFields("google callback missing state or code", logger.Fields{
				"state":       state,
				"code":        code,
				"redirect_to": redirectURL,
				"request_id":  c.Request.Header.Get("X-Request-Id"),
				"span_id":     c.Request.Header.Get("X-Span-Id"),
			})
			c.Redirect(http.StatusFound, redirectURL)
			return
		}

		cookieState, err := c.Cookie(oauthStateCookieName)
		if err != nil {
			logger.ErrorWithFields("google callback state cookie not found", logger.Fields{
				"state":       state,
				"error":       err.Error(),
				"redirect_to": redirectURL,
				"request_id":  c.Request.Header.Get("X-Request-Id"),
				"span_id":     c.Request.Header.Get("X-Span-Id"),
			})
			c.Redirect(http.StatusFound, redirectURL)
			return
		}

		// 재사용 방지를 위해 콜백 시점에 state 쿠키를 즉시 만료시킨다.
		c.SetCookie(oauthStateCookieName, "", -1, "/", "", false, true)

		if cookieState != state {
			logger.ErrorWithFields("google callback invalid state", logger.Fields{
				"cookie_state": cookieState,
				"state":        state,
				"redirect_to":  redirectURL,
				"request_id":   c.Request.Header.Get("X-Request-Id"),
				"span_id":      c.Request.Header.Get("X-Span-Id"),
			})
			c.Redirect(http.StatusFound, redirectURL)
			return
		}

		sessionID, err := authSvc.HandleGoogleCallback(c.Request.Context(), code)
		if err != nil {
			logger.ErrorWithFields("google callback failed", logger.Fields{
				"error":       err.Error(),
				"redirect_to": redirectURL,
				"request_id":  c.Request.Header.Get("X-Request-Id"),
				"span_id":     c.Request.Header.Get("X-Span-Id"),
			})
			c.Redirect(http.StatusFound, redirectURL)
			return
		}

		redirectWithSession := authSvc.GetRedirectURLWithSession(sessionID)
		logger.InfoWithFields("redirect to login success with session", logger.Fields{
			"redirect_to": redirectWithSession,
			"request_id":  c.Request.Header.Get("X-Request-Id"),
			"span_id":     c.Request.Header.Get("X-Span-Id"),
		})
		c.Redirect(http.StatusFound, redirectWithSession)
	}
}

type sessionExchangeRequest struct {
	Session string `json:"session"`
}

// SessionExchangeHandler godoc
// @Summary      로그인 세션을 JWT 액세스 토큰으로 교환
// @Description  짧은 TTL을 가진 session ID를 받아, 유저 서비스에 위임해 JWT 액세스 토큰으로 교환합니다.
// @Tags         auth
// @Accept       json
// @Produce      json
// @Param        body  body      sessionExchangeRequest  true  "세션 교환 요청"
// @Success      200   {object}  map[string]string       "access_token 포함"
// @Failure      400   {object}  map[string]string       "세션 만료 또는 유효하지 않음"
// @Router       /auth/session/exchange [post]
func SessionExchangeHandler(authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req sessionExchangeRequest
		if err := c.ShouldBindJSON(&req); err != nil || strings.TrimSpace(req.Session) == "" {
			logger.ErrorWithFields("session exchange failed", logger.Fields{
				"error":      err.Error(),
				"request_id": c.Request.Header.Get("X-Request-Id"),
				"span_id":    c.Request.Header.Get("X-Span-Id"),
			})
			c.JSON(http.StatusBadRequest, gin.H{
				"message": "로그인 세션이 만료되었거나 유효하지 않습니다.",
			})
			return
		}

		accessToken, err := authSvc.ExchangeLoginSession(c.Request.Context(), req.Session)
		if err != nil {
			logger.ErrorWithFields("session exchange failed", logger.Fields{
				"error":      err.Error(),
				"request_id": c.Request.Header.Get("X-Request-Id"),
				"span_id":    c.Request.Header.Get("X-Span-Id"),
			})
			c.JSON(http.StatusBadRequest, gin.H{
				"message": "로그인 세션이 만료되었거나 유효하지 않습니다.",
			})
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"access_token": accessToken,
		})
	}
}

// GetUserProfileHandler godoc
// @Summary      현재 로그인한 사용자 프로필 조회
// @Description  Authorization 헤더에 포함된 JWT를 검증하고, 현재 로그인한 사용자의 프로필 정보를 조회합니다.
// @Tags         users
// @Param        Authorization  header  string  true  "Bearer 액세스 토큰 (예: Bearer eyJ...)"
// @Produce      json
// @Success      200  {object}  dto.UserProfileDTO
// @Failure      401  {object}  dto.ErrorResponseDTO
// @Failure      404  {object}  dto.ErrorResponseDTO
// @Failure      500  {object}  dto.ErrorResponseDTO
// @Router       /users/profile [get]
func GetUserProfileHandler(authSvc *services.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userCode, ok := requireUserCodeFromHeader(c, authSvc)
		if !ok {
			return
		}

		profile, err := authSvc.GetUserProfile(c.Request.Context(), userCode)
		if err != nil {
			if errors.Is(err, services.ErrUserNotFound) {
				c.JSON(http.StatusNotFound, gin.H{"error": "user_not_found"})
				return
			}
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed_to_load_profile"})
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"user_code":     profile.UserCode,
			"provider":      profile.Provider,
			"provider_sub":  profile.ProviderSub,
			"email":         profile.Email,
			"name":          profile.Name,
			"profile_image": profile.ProfileImage,
			"role":          profile.Role,
			"created_at":    profile.CreatedAt.Format(time.RFC3339),
			"updated_at":    profile.UpdatedAt.Format(time.RFC3339),
		})
	}
}
