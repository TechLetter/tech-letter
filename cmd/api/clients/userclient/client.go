package userclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"time"

	"tech-letter/cmd/api/httpclient"
)

// Client는 Python user-service HTTP API를 호출하는 얇은 클라이언트다.
//
// - 인증/인가 로직은 API Gateway(Go cmd/api)에서 처리하고, 이 클라이언트는
//   순수하게 유저 데이터(upsert/조회)만 호출한다.
//
// baseURL 예: http://user_service:8002

type Client struct {
	base *httpclient.BaseClient
}

var (
	ErrNotFound = fmt.Errorf("resource not found")
)

func New() *Client {
	base := os.Getenv("USER_SERVICE_BASE_URL")
	if base == "" {
		base = "http://user_service:8002"
	}

	return &Client{
		base: httpclient.NewBaseClient(base),
	}
}

// -------------------- DTOs --------------------

type UpsertRequest struct {
	Provider     string `json:"provider"`
	ProviderSub  string `json:"provider_sub"`
	Email        string `json:"email"`
	Name         string `json:"name"`
	ProfileImage string `json:"profile_image"`
}

type UpsertResponse struct {
	UserCode string `json:"user_code"`
	Role     string `json:"role"`
}

type UserProfileResponse struct {
	UserCode     string    `json:"user_code"`
	Provider     string    `json:"provider"`
	ProviderSub  string    `json:"provider_sub"`
	Email        string    `json:"email"`
	Name         string    `json:"name"`
	ProfileImage string    `json:"profile_image"`
	Role         string    `json:"role"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

// -------------------- Methods --------------------

func (c *Client) UpsertUser(ctx context.Context, req UpsertRequest) (UpsertResponse, error) {
	bodyBytes, err := json.Marshal(req)
	if err != nil {
		return UpsertResponse{}, err
	}

	httpReq, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/users/upsert", nil, bytes.NewReader(bodyBytes))
	if err != nil {
		return UpsertResponse{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(httpReq)
	if err != nil {
		return UpsertResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return UpsertResponse{}, ErrNotFound
	}

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return UpsertResponse{}, fmt.Errorf("user-service UpsertUser: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out UpsertResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return UpsertResponse{}, err
	}
	return out, nil
}

func (c *Client) GetUserProfile(ctx context.Context, userCode string) (UserProfileResponse, error) {
	relPath := path.Join("/api/v1/users", userCode)
	httpReq, err := c.base.NewRequest(ctx, http.MethodGet, relPath, nil, nil)
	if err != nil {
		return UserProfileResponse{}, err
	}

	resp, err := c.base.Do(httpReq)
	if err != nil {
		return UserProfileResponse{}, err
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK:
		var out UserProfileResponse
		if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
			return UserProfileResponse{}, err
		}
		return out, nil
	case http.StatusNotFound:
		return UserProfileResponse{}, ErrNotFound
	default:
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return UserProfileResponse{}, fmt.Errorf("user-service GetUserProfile: status=%d body=%s", resp.StatusCode, string(body))
	}
}
