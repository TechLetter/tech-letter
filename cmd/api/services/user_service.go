package services

import (
	"context"
	"errors"
	"fmt"
	"time"

	"tech-letter/cmd/api/clients/userclient"
	"tech-letter/cmd/api/dto"
)

type UserService struct {
	userClient *userclient.Client
}

func NewUserService(userClient *userclient.Client) *UserService {
	return &UserService{
		userClient: userClient,
	}
}

// UpsertUser 는 소셜 로그인 시 유저 정보를 갱신하거나 생성한다.
func (s *UserService) UpsertUser(ctx context.Context, req userclient.UpsertRequest) (userclient.UpsertResponse, error) {
	resp, err := s.userClient.UpsertUser(ctx, req)
	if err != nil {
		return userclient.UpsertResponse{}, fmt.Errorf("user upsert: %w", err)
	}
	return resp, nil
}

// GetUserProfile 은 유저 프로필을 조회한다.
func (s *UserService) GetUserProfile(ctx context.Context, userCode string) (userclient.UserProfileResponse, error) {
	profile, err := s.userClient.GetUserProfile(ctx, userCode)
	if err != nil {
		if errors.Is(err, userclient.ErrNotFound) {
			return userclient.UserProfileResponse{}, ErrUserNotFound
		}
		return userclient.UserProfileResponse{}, err
	}
	return profile, nil
}

// CreateLoginSession 은 로그인 세션을 생성한다.
func (s *UserService) CreateLoginSession(ctx context.Context, sessionID, accessToken string, expiresAt time.Time) error {
	return s.userClient.CreateLoginSession(ctx, sessionID, accessToken, expiresAt)
}

// ExchangeLoginSession 은 로그인 세션을 JWT로 교환한다.
func (s *UserService) ExchangeLoginSession(ctx context.Context, sessionID string) (string, error) {
	return s.userClient.ExchangeLoginSession(ctx, sessionID)
}

// --- Chat Session Methods ---

func (s *UserService) CreateSession(ctx context.Context, userCode string) (*dto.ChatSession, error) {
	return s.userClient.CreateSession(ctx, userCode)
}

func (s *UserService) ListSessions(ctx context.Context, userCode string, page, pageSize int) (*dto.ListSessionsResponse, error) {
	return s.userClient.ListSessions(ctx, userCode, page, pageSize)
}

func (s *UserService) GetSession(ctx context.Context, userCode, sessionID string) (*dto.ChatSession, error) {
	return s.userClient.GetSession(ctx, userCode, sessionID)
}

func (s *UserService) DeleteSession(ctx context.Context, userCode, sessionID string) error {
	return s.userClient.DeleteSession(ctx, userCode, sessionID)
}

// DeleteUser 는 유저를 삭제한다.
func (s *UserService) DeleteUser(ctx context.Context, userCode string) error {
	if err := s.userClient.DeleteUser(ctx, userCode); err != nil {
		if errors.Is(err, userclient.ErrNotFound) {
			return ErrUserNotFound
		}
		return err
	}
	return nil
}

// GrantDailyCredits 는 유저에게 일일 크레딧을 지급한다.
func (s *UserService) GrantDailyCredits(ctx context.Context, userCode string) error {
	_, err := s.userClient.GrantDailyCredits(ctx, userCode)
	return err
}

// GetCredits 는 유저의 크레딧 잔액을 조회한다.
func (s *UserService) GetCredits(ctx context.Context, userCode string) (userclient.CreditSummaryResponse, error) {
	return s.userClient.GetCredits(ctx, userCode)
}
