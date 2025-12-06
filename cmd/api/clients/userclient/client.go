package userclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
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

// -------------------- Login Session DTOs --------------------

type LoginSessionCreateRequest struct {
	SessionID string    `json:"session_id"`
	JWTToken  string    `json:"jwt_token"`
	ExpiresAt time.Time `json:"expires_at"`
}

type LoginSessionCreateResponse struct {
	SessionID string `json:"session_id"`
}

type LoginSessionDeleteResponse struct {
	JWTToken string `json:"jwt_token"`
}

// -------------------- Bookmark DTOs --------------------

type BookmarkCreateRequest struct {
	UserCode string `json:"user_code"`
	PostID   string `json:"post_id"`
}

type BookmarkItem struct {
	PostID    string    `json:"post_id"`
	CreatedAt time.Time `json:"created_at"`
}

type ListBookmarksResponse struct {
	Total int            `json:"total"`
	Items []BookmarkItem `json:"items"`
}

type BookmarkCheckRequest struct {
	UserCode string   `json:"user_code"`
	PostIDs  []string `json:"post_ids"`
}

type BookmarkCheckResponse struct {
	BookmarkedPostIDs []string `json:"bookmarked_post_ids"`
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

// CreateLoginSession는 POST /api/v1/login-sessions 를 호출해
// Gateway에서 생성한 session_id, jwt_token, expires_at 을 저장한다.
func (c *Client) CreateLoginSession(ctx context.Context, sessionID string, jwtToken string, expiresAt time.Time) error {
	bodyBytes, err := json.Marshal(LoginSessionCreateRequest{
		SessionID: sessionID,
		JWTToken:  jwtToken,
		ExpiresAt: expiresAt,
	})
	if err != nil {
		return err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/login-sessions", nil, bytes.NewReader(bodyBytes))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("user-service CreateLoginSession: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out LoginSessionCreateResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return err
	}
	_ = out // 현재는 세션 ID를 호출 측에서 이미 알고 있으므로 응답 값은 검증 용도로만 사용한다.
	return nil
}

// ExchangeLoginSession는 DELETE /api/v1/login-sessions/{session_id} 를 호출해
// 세션을 삭제하고, 저장되어 있던 JWT 토큰을 반환한다. 세션이 없거나 만료된 경우 에러를 반환한다.
func (c *Client) ExchangeLoginSession(ctx context.Context, sessionID string) (string, error) {
	relPath := path.Join("/api/v1/login-sessions", sessionID)
	req, err := c.base.NewRequest(ctx, http.MethodDelete, relPath, nil, nil)
	if err != nil {
		return "", err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return "", fmt.Errorf("user-service DeleteLoginSession: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out LoginSessionDeleteResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", err
	}
	return out.JWTToken, nil
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

// -------------------- Bookmark Methods --------------------

// AddBookmark는 POST /api/v1/bookmarks 를 호출해 유저 북마크를 추가한다.
func (c *Client) AddBookmark(ctx context.Context, userCode, postID string) (BookmarkItem, error) {
	body := BookmarkCreateRequest{UserCode: userCode, PostID: postID}
	buf, err := json.Marshal(body)
	if err != nil {
		return BookmarkItem{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/bookmarks", nil, bytes.NewReader(buf))
	if err != nil {
		return BookmarkItem{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return BookmarkItem{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return BookmarkItem{}, fmt.Errorf("user-service AddBookmark: status=%d body=%s", resp.StatusCode, string(bodyBytes))
	}

	var out BookmarkItem
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return BookmarkItem{}, err
	}
	return out, nil
}

// RemoveBookmark는 DELETE /api/v1/bookmarks 를 호출해 유저 북마크를 삭제한다.
func (c *Client) RemoveBookmark(ctx context.Context, userCode, postID string) error {
	body := BookmarkCreateRequest{UserCode: userCode, PostID: postID}
	buf, err := json.Marshal(body)
	if err != nil {
		return err
	}

	req, err := c.base.NewRequest(ctx, http.MethodDelete, "/api/v1/bookmarks", nil, bytes.NewReader(buf))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK:
		return nil
	case http.StatusNotFound:
		return ErrNotFound
	default:
		bodyBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("user-service RemoveBookmark: status=%d body=%s", resp.StatusCode, string(bodyBytes))
	}
}

// ListBookmarks는 GET /api/v1/bookmarks 를 호출해 유저의 북마크 목록을 조회한다.
func (c *Client) ListBookmarks(ctx context.Context, userCode string, page, pageSize int) (ListBookmarksResponse, error) {
	q := url.Values{}
	q.Set("user_code", userCode)
	if page > 0 {
		q.Set("page", fmt.Sprint(page))
	}
	if pageSize > 0 {
		q.Set("page_size", fmt.Sprint(pageSize))
	}

	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/bookmarks", q, nil)
	if err != nil {
		return ListBookmarksResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return ListBookmarksResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return ListBookmarksResponse{}, fmt.Errorf("user-service ListBookmarks: status=%d body=%s", resp.StatusCode, string(bodyBytes))
	}

	var out ListBookmarksResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return ListBookmarksResponse{}, err
	}
	return out, nil
}

// CheckBookmarks는 POST /api/v1/bookmarks/check 를 호출해 여러 포스트에 대한 북마크 여부를 조회한다.
func (c *Client) CheckBookmarks(ctx context.Context, userCode string, postIDs []string) (BookmarkCheckResponse, error) {
	body := BookmarkCheckRequest{UserCode: userCode, PostIDs: postIDs}
	buf, err := json.Marshal(body)
	if err != nil {
		return BookmarkCheckResponse{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/bookmarks/check", nil, bytes.NewReader(buf))
	if err != nil {
		return BookmarkCheckResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return BookmarkCheckResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return BookmarkCheckResponse{}, fmt.Errorf("user-service CheckBookmarks: status=%d body=%s", resp.StatusCode, string(bodyBytes))
	}

	var out BookmarkCheckResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return BookmarkCheckResponse{}, err
	}
	return out, nil
}
