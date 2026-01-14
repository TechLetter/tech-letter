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

	"tech-letter/cmd/api/dto"
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

// DeleteUser는 DELETE /api/v1/users/{user_code} 를 호출해 유저와 해당 유저의 북마크를 삭제한다.
func (c *Client) DeleteUser(ctx context.Context, userCode string) error {
	relPath := path.Join("/api/v1/users", userCode)
	req, err := c.base.NewRequest(ctx, http.MethodDelete, relPath, nil, nil)
	if err != nil {
		return err
	}

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
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("user-service DeleteUser: status=%d body=%s", resp.StatusCode, string(body))
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

// UserProfileResponse는 dto.UserProfileDTO를 사용하여 중복을 제거.
// 하지만 userclient는 dto를 import하면 순환참조 위험이 있으므로 별도 유지.
// 대신 필드를 동일하게 유지하여 JSON 매핑 호환성 보장.
type UserProfileResponse struct {
	UserCode     string    `json:"user_code"`
	Provider     string    `json:"provider"`
	ProviderSub  string    `json:"provider_sub"`
	Email        string    `json:"email"`
	Name         string    `json:"name"`
	ProfileImage string    `json:"profile_image"`
	Role         string    `json:"role"`
	Credits      int       `json:"credits"`
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
	Total    int            `json:"total"`
	Items    []BookmarkItem `json:"items"`
	Page     int            `json:"page"`
	PageSize int            `json:"page_size"`
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

// -------------------- Admin Methods --------------------

type ListUsersResponse struct {
	Total int                   `json:"total"`
	Items []UserProfileResponse `json:"items"`
}

func (c *Client) ListUsers(ctx context.Context, page, pageSize int) (ListUsersResponse, error) {
	q := url.Values{}
	if page > 0 {
		q.Set("page", fmt.Sprint(page))
	}
	if pageSize > 0 {
		q.Set("page_size", fmt.Sprint(pageSize))
	}

	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/users", q, nil)
	if err != nil {
		return ListUsersResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return ListUsersResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return ListUsersResponse{}, fmt.Errorf("user-service ListUsers: status=%d body=%s", resp.StatusCode, string(b))
	}

	var out ListUsersResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return ListUsersResponse{}, err
	}
	return out, nil
}

// -------------------- Credit DTOs --------------------

// CreditResponse는 크레딧 조회/소비 응답.
type CreditResponse struct {
	Remaining int    `json:"remaining"`
	Granted   int    `json:"granted,omitempty"`
	ExpiredAt string `json:"expired_at"`
}

// CreditSummaryResponse는 1:N 크레딧 집계 응답.
type CreditSummaryResponse struct {
	TotalRemaining int          `json:"total_remaining"`
	Credits        []CreditItem `json:"credits"`
}

// CreditItem은 개별 크레딧 정보.
type CreditItem struct {
	ID             string `json:"id"`
	Amount         int    `json:"amount"`
	OriginalAmount int    `json:"original_amount"`
	Source         string `json:"source"`
	Reason         string `json:"reason"`
	ExpiredAt      string `json:"expired_at"`
}

// ConsumeCreditsRequest는 크레딧 소비 요청.
type ConsumeCreditsRequest struct {
	Amount int    `json:"amount"`
	Reason string `json:"reason,omitempty"`
}

// GrantDailyResponse는 일일 크레딧 지급 응답.
type GrantDailyResponse struct {
	Granted        int  `json:"granted"`
	AlreadyGranted bool `json:"already_granted"`
}

// GrantCreditsRequest는 관리자 크레딧 부여 요청.
type GrantCreditsRequest struct {
	ExpiredAt string `json:"expired_at"`
	Amount    int    `json:"amount"`
	Source    string `json:"source"`
	Reason    string `json:"reason"`
}

// ErrInsufficientCredits는 크레딧 부족 에러.
var ErrInsufficientCredits = fmt.Errorf("insufficient credits")

// -------------------- Credit Methods --------------------

// GetCredits는 GET /api/v1/credits/{user_code} 를 호출해 유저의 크레딧 잔액을 조회한다.
func (c *Client) GetCredits(ctx context.Context, userCode string) (CreditSummaryResponse, error) {
	relPath := path.Join("/api/v1/credits", userCode)
	req, err := c.base.NewRequest(ctx, http.MethodGet, relPath, nil, nil)
	if err != nil {
		return CreditSummaryResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return CreditSummaryResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return CreditSummaryResponse{}, fmt.Errorf("user-service GetCredits: status=%d body=%s", resp.StatusCode, string(b))
	}

	var out CreditSummaryResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return CreditSummaryResponse{}, err
	}
	return out, nil
}

// ConsumeCredits는 POST /api/v1/credits/{user_code}/consume 를 호출해 크레딧을 소비한다.
// 크레딧 부족 시 ErrInsufficientCredits를 반환한다.
func (c *Client) ConsumeCredits(ctx context.Context, userCode string, amount int) (CreditResponse, error) {
	relPath := path.Join("/api/v1/credits", userCode, "consume")
	body := ConsumeCreditsRequest{Amount: amount}
	buf, err := json.Marshal(body)
	if err != nil {
		return CreditResponse{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, bytes.NewReader(buf))
	if err != nil {
		return CreditResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return CreditResponse{}, err
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK:
		var out CreditResponse
		if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
			return CreditResponse{}, err
		}
		return out, nil
	case http.StatusPaymentRequired:
		return CreditResponse{}, ErrInsufficientCredits
	default:
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return CreditResponse{}, fmt.Errorf("user-service ConsumeCredits: status=%d body=%s", resp.StatusCode, string(b))
	}
}

// GrantCredits는 POST /api/v1/credits/{user_code}/grant 를 호출해 크레딧을 부여한다.
func (c *Client) GrantCredits(ctx context.Context, userCode string, amount int, source, reason, expiredAt string) (CreditSummaryResponse, error) {
	relPath := path.Join("/api/v1/credits", userCode, "grant")

	body := GrantCreditsRequest{
		ExpiredAt: expiredAt,
		Amount:    amount,
		Source:    source,
		Reason:    reason,
	}
	buf, err := json.Marshal(body)
	if err != nil {
		return CreditSummaryResponse{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, bytes.NewReader(buf))
	if err != nil {
		return CreditSummaryResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return CreditSummaryResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return CreditSummaryResponse{}, fmt.Errorf("user-service GrantCredits: status=%d body=%s", resp.StatusCode, string(b))
	}

	var out CreditSummaryResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return CreditSummaryResponse{}, err
	}
	return out, nil
}

// GrantDailyCredits는 POST /api/v1/credits/{user_code}/grant-daily 를 호출해 일일 크레딧을 지급한다.
func (c *Client) GrantDailyCredits(ctx context.Context, userCode string) (GrantDailyResponse, error) {
	relPath := path.Join("/api/v1/credits", userCode, "grant-daily")

	req, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, nil)
	if err != nil {
		return GrantDailyResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return GrantDailyResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return GrantDailyResponse{}, fmt.Errorf("user-service GrantDailyCredits: status=%d body=%s", resp.StatusCode, string(b))
	}

	var out GrantDailyResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return GrantDailyResponse{}, err
	}
	return out, nil
}

// ConsumeCreditsResponse는 크레딧 소비 응답 (consume_id 포함).
type ConsumeCreditsResponse struct {
	Remaining         int      `json:"remaining"`
	ConsumeID         string   `json:"consume_id"`
	ConsumedCreditIDs []string `json:"consumed_credit_ids"`
}

// ConsumeCreditsWithID는 POST /api/v1/credits/{user_code}/consume 를 호출해 크레딧을 소비하고 consume_id를 반환한다.
func (c *Client) ConsumeCreditsWithID(ctx context.Context, userCode string, amount int, reason string) (ConsumeCreditsResponse, error) {
	relPath := path.Join("/api/v1/credits", userCode, "consume")
	body := map[string]any{"amount": amount, "reason": reason}
	buf, err := json.Marshal(body)
	if err != nil {
		return ConsumeCreditsResponse{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, bytes.NewReader(buf))
	if err != nil {
		return ConsumeCreditsResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return ConsumeCreditsResponse{}, err
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK:
		var out ConsumeCreditsResponse
		if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
			return ConsumeCreditsResponse{}, err
		}
		return out, nil
	case http.StatusPaymentRequired:
		return ConsumeCreditsResponse{}, ErrInsufficientCredits
	default:
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return ConsumeCreditsResponse{}, fmt.Errorf("user-service ConsumeCredits: status=%d body=%s", resp.StatusCode, string(b))
	}
}

// LogChatRequest는 채팅 로그 요청.
type LogChatRequest struct {
	ConsumeID         string   `json:"consume_id"`
	ConsumedCreditIDs []string `json:"consumed_credit_ids"`
	Query             string   `json:"query"`
	Success           bool     `json:"success"`
	Answer            *string  `json:"answer,omitempty"`
	ErrorCode         *string  `json:"error_code,omitempty"`
	SessionID         *string  `json:"session_id,omitempty"`
}

// LogChatResponse는 채팅 로그 응답.
type LogChatResponse struct {
	EventID string `json:"event_id"`
}

// LogChatCompleted는 POST /api/v1/credits/{user_code}/log-chat 를 호출해 채팅 성공 이벤트를 발행한다.
func (c *Client) LogChatCompleted(ctx context.Context, userCode, consumeID string, consumedCreditIDs []string, query, answer string, sessionID string) (LogChatResponse, error) {
	req := LogChatRequest{
		ConsumeID:         consumeID,
		ConsumedCreditIDs: consumedCreditIDs,
		Query:             query,
		Success:           true,
		Answer:            &answer,
	}
	if sessionID != "" {
		req.SessionID = &sessionID
	}
	return c.logChat(ctx, userCode, req)
}

// LogChatFailed는 POST /api/v1/credits/{user_code}/log-chat 를 호출해 채팅 실패 이벤트를 발행하고 환불을 처리한다.
func (c *Client) LogChatFailed(ctx context.Context, userCode, consumeID string, consumedCreditIDs []string, query, errorCode string, sessionID string) (LogChatResponse, error) {
	req := LogChatRequest{
		ConsumeID:         consumeID,
		ConsumedCreditIDs: consumedCreditIDs,
		Query:             query,
		Success:           false,
		ErrorCode:         &errorCode,
	}
	if sessionID != "" {
		req.SessionID = &sessionID
	}
	return c.logChat(ctx, userCode, req)
}

func (c *Client) logChat(ctx context.Context, userCode string, body LogChatRequest) (LogChatResponse, error) {
	relPath := path.Join("/api/v1/credits", userCode, "log-chat")
	buf, err := json.Marshal(body)
	if err != nil {
		return LogChatResponse{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, bytes.NewReader(buf))
	if err != nil {
		return LogChatResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return LogChatResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return LogChatResponse{}, fmt.Errorf("user-service LogChat: status=%d body=%s", resp.StatusCode, string(b))
	}

	var out LogChatResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return LogChatResponse{}, err
	}
	return out, nil
}

// -------------------- Chat Session Methods --------------------

func (c *Client) ListSessions(ctx context.Context, userCode string, page, pageSize int) (*dto.ListSessionsResponse, error) {
	query := url.Values{}
	query.Set("user_code", userCode)
	query.Set("page", fmt.Sprintf("%d", page))
	query.Set("page_size", fmt.Sprintf("%d", pageSize))
	req, err := c.base.NewRequest(ctx, "GET", "/api/v1/chatbot/sessions", query, nil)
	if err != nil {
		return nil, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to list sessions: status %d", resp.StatusCode)
	}

	var result dto.ListSessionsResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *Client) GetSession(ctx context.Context, userCode, sessionID string) (*dto.ChatSession, error) {
	query := url.Values{}
	query.Set("user_code", userCode)
	req, err := c.base.NewRequest(ctx, "GET", fmt.Sprintf("/api/v1/chatbot/sessions/%s", sessionID), query, nil)
	if err != nil {
		return nil, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		if resp.StatusCode == http.StatusNotFound {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to get session: status %d", resp.StatusCode)
	}

	var result dto.ChatSession
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *Client) CreateSession(ctx context.Context, userCode string) (*dto.ChatSession, error) {
	query := url.Values{}
	query.Set("user_code", userCode)
	req, err := c.base.NewRequest(ctx, "POST", "/api/v1/chatbot/sessions", query, nil)
	if err != nil {
		return nil, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to create session: status %d", resp.StatusCode)
	}

	var result dto.ChatSession
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *Client) DeleteSession(ctx context.Context, userCode, sessionID string) error {
	query := url.Values{}
	query.Set("user_code", userCode)
	req, err := c.base.NewRequest(ctx, "DELETE", fmt.Sprintf("/api/v1/chatbot/sessions/%s", sessionID), query, nil)
	if err != nil {
		return err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("failed to delete session: status %d", resp.StatusCode)
	}
	return nil
}

// GrantCreditInternal grants credits using internal request format (includes source/reason).
func (c *Client) GrantCreditInternal(ctx context.Context, userCode string, req *dto.GrantCreditInternalRequest) (*dto.GrantCreditResponseDTO, error) {
	relPath := fmt.Sprintf("/api/v1/credits/%s/grant", userCode)
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}

	httpReq, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	httpResp, err := c.base.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("grant credit failed: %s", httpResp.Status)
	}

	var result dto.GrantCreditResponseDTO
	if err := json.NewDecoder(httpResp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return &result, nil
}
