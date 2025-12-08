package services

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"os"
	"time"

	"tech-letter/cmd/api/auth"
	"tech-letter/cmd/api/clients/userclient"
)

type AuthService struct {
	googleOAuth *auth.GoogleOAuthClient
	userClient  *userclient.Client
	jwtManager  *auth.JWTManager
	redirectURL string
}

var ErrUserNotFound = errors.New("user not found")

// 로그인 세션 TTL. (임시 OAuth 세션의 만료 시간)
const loginSessionTTL = 60 * time.Second

func NewAuthService(googleOAuth *auth.GoogleOAuthClient, userClient *userclient.Client, jwtManager *auth.JWTManager, redirectURL string) *AuthService {
	return &AuthService{
		googleOAuth: googleOAuth,
		userClient:  userClient,
		jwtManager:  jwtManager,
		redirectURL: redirectURL,
	}
}

func NewAuthServiceFromEnv() (*AuthService, error) {
	googleClient, err := auth.NewGoogleOAuthClientFromEnv()
	if err != nil {
		return nil, fmt.Errorf("failed to init GoogleOAuthClient: %w", err)
	}

	jwtManager, err := auth.NewJWTManagerFromEnv()
	if err != nil {
		return nil, fmt.Errorf("failed to init JWTManager: %w", err)
	}

	redirectURL := os.Getenv("AUTH_LOGIN_SUCCESS_REDIRECT_URL")
	if redirectURL == "" {
		return nil, fmt.Errorf("AUTH_LOGIN_SUCCESS_REDIRECT_URL is blank")
	}
	userClient := userclient.New()

	return NewAuthService(googleClient, userClient, jwtManager, redirectURL), nil
}

func (s *AuthService) BuildGoogleLoginURL(state string) string {
	return s.googleOAuth.AuthCodeURL(state)
}

func (s *AuthService) HandleGoogleCallback(ctx context.Context, code string) (string, error) {
	token, err := s.googleOAuth.Exchange(ctx, code)
	if err != nil {
		return "", fmt.Errorf("google oauth exchange: %w", err)
	}

	info, err := s.googleOAuth.FetchUserInfo(ctx, token)
	if err != nil {
		return "", fmt.Errorf("google userinfo: %w", err)
	}

	upsertResp, err := s.userClient.UpsertUser(ctx, userclient.UpsertRequest{
		Provider:     "google",
		ProviderSub:  info.Sub,
		Email:        info.Email,
		Name:         info.Name,
		ProfileImage: info.Picture,
	})
	if err != nil {
		return "", fmt.Errorf("user upsert: %w", err)
	}

	accessToken, err := s.jwtManager.Sign(upsertResp.UserCode, upsertResp.Role)
	if err != nil {
		return "", fmt.Errorf("jwt sign: %w", err)
	}

	sessionID, err := generateSessionID()
	if err != nil {
		return "", fmt.Errorf("generate login session id: %w", err)
	}
	expiresAt := time.Now().Add(loginSessionTTL)
	if err := s.userClient.CreateLoginSession(ctx, sessionID, accessToken, expiresAt); err != nil {
		return "", fmt.Errorf("create login session: %w", err)
	}
	return sessionID, nil
}

// ExchangeLoginSession 는 짧은 TTL을 가진 로그인 세션을 JWT 액세스 토큰으로 교환한다.
func (s *AuthService) ExchangeLoginSession(ctx context.Context, sessionID string) (string, error) {
	jwtToken, err := s.userClient.ExchangeLoginSession(ctx, sessionID)
	if err != nil {
		return "", fmt.Errorf("exchange login session: %w", err)
	}
	return jwtToken, nil
}

// GetRedirectURL 는 Google OAuth 플로우 최종 리다이렉트 대상 URL을 반환한다.
// 성공 시에는 GetRedirectURLWithSession 으로 세션 ID 를 붙여 사용하고,
// 실패 시에는 이 URL로 세션 없이 리다이렉트한다.
func (s *AuthService) GetRedirectURL() string {
	return s.redirectURL
}

func (s *AuthService) GetRedirectURLWithSession(sessionID string) string {
	return fmt.Sprintf("%s?session=%s", s.redirectURL, sessionID)
}

func (s *AuthService) ParseAccessToken(token string) (string, string, error) {
	return s.jwtManager.Parse(token)
}

func (s *AuthService) GetUserProfile(ctx context.Context, userCode string) (userclient.UserProfileResponse, error) {
	profile, err := s.userClient.GetUserProfile(ctx, userCode)
	if err != nil {
		if errors.Is(err, userclient.ErrNotFound) {
			return userclient.UserProfileResponse{}, ErrUserNotFound
		}
		return userclient.UserProfileResponse{}, err
	}
	return profile, nil
}

// DeleteUser 는 주어진 userCode 에 해당하는 유저와 북마크를 삭제한다.
func (s *AuthService) DeleteUser(ctx context.Context, userCode string) error {
	if err := s.userClient.DeleteUser(ctx, userCode); err != nil {
		if errors.Is(err, userclient.ErrNotFound) {
			return ErrUserNotFound
		}
		return err
	}
	return nil
}

func generateSessionID() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}
