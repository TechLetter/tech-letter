package contentclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path"
	"strconv"
	"time"
)

// Client는 Python content-service HTTP API를 호출하는 얇은 클라이언트다.
//
// - 인증/유저 로직은 전혀 알지 않고, 순수하게 콘텐츠 데이터만 가져온다.
// - API Gateway(Go cmd/api)에서 이 클라이언트를 사용해 DTO를 조합한다.
//
// baseURL 예: http://content_service:8001

type Client struct {
	httpClient *http.Client
	baseURL    string
}

var ErrNotFound = errors.New("resource not found")

func New() *Client {
	base := os.Getenv("CONTENT_SERVICE_BASE_URL")
	if base == "" {
		base = "http://content_service:8001"
	}

	return &Client{
		httpClient: &http.Client{Timeout: 10 * time.Second},
		baseURL:    base,
	}
}

// -------------------- Posts --------------------

type ListPostsParams struct {
	Page       int
	PageSize   int
	Categories []string
	Tags       []string
	BlogID     string
	BlogName   string
	// Status Filters (추후 DocumentEmbedded 등 추가 가능)
	StatusAISummarized *bool
}

type ListPostsResponse struct {
	Total int        `json:"total"`
	Items []PostItem `json:"items"`
}

type PostItem struct {
	ID           string    `json:"id"`
	ViewCount    int       `json:"view_count"`
	BlogID       string    `json:"blog_id"`
	BlogName     string    `json:"blog_name"`
	Title        string    `json:"title"`
	Link         string    `json:"link"`
	PublishedAt  time.Time `json:"published_at"`
	ThumbnailURL string    `json:"thumbnail_url"`
	AISummary    AISummary `json:"aisummary"`
}

type AISummary struct {
	Categories []string `json:"categories"`
	Tags       []string `json:"tags"`
	Summary    string   `json:"summary"`
}

func (c *Client) ListPosts(ctx context.Context, params ListPostsParams) (ListPostsResponse, error) {
	u, err := url.Parse(c.baseURL + "/api/v1/posts")
	if err != nil {
		return ListPostsResponse{}, err
	}

	q := u.Query()
	if params.Page > 0 {
		q.Set("page", strconv.Itoa(params.Page))
	}
	if params.PageSize > 0 {
		q.Set("page_size", strconv.Itoa(params.PageSize))
	}
	for _, cat := range params.Categories {
		q.Add("categories", cat)
	}
	for _, tag := range params.Tags {
		q.Add("tags", tag)
	}
	if params.BlogID != "" {
		q.Set("blog_id", params.BlogID)
	}
	if params.BlogName != "" {
		q.Set("blog_name", params.BlogName)
	}
	if params.StatusAISummarized != nil {
		q.Set("status_ai_summarized", strconv.FormatBool(*params.StatusAISummarized))
	}
	u.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return ListPostsResponse{}, err
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return ListPostsResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return ListPostsResponse{}, fmt.Errorf("content-service ListPosts: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out ListPostsResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return ListPostsResponse{}, err
	}
	return out, nil
}

// GetPost는 단일 포스트를 조회한다.
// 존재하지 않으면 ErrNotFound 를 반환한다.
func (c *Client) GetPost(ctx context.Context, id string) (PostItem, error) {
	// /api/v1/posts/{id}
	u, err := url.Parse(c.baseURL)
	if err != nil {
		return PostItem{}, err
	}
	u.Path = path.Join(u.Path, "/api/v1/posts/", id)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return PostItem{}, err
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return PostItem{}, err
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK:
		var out PostItem
		if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
			return PostItem{}, err
		}
		return out, nil
	case http.StatusNotFound:
		return PostItem{}, ErrNotFound
	default:
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return PostItem{}, fmt.Errorf("content-service GetPost: status=%d body=%s", resp.StatusCode, string(body))
	}
}

// -------------------- Blogs --------------------

type ListBlogsParams struct {
	Page     int
	PageSize int
}

type ListBlogsResponse struct {
	Total int        `json:"total"`
	Items []BlogItem `json:"items"`
}

type BlogItem struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	URL  string `json:"url"`
}

func (c *Client) ListBlogs(ctx context.Context, params ListBlogsParams) (ListBlogsResponse, error) {
	u, err := url.Parse(c.baseURL + "/api/v1/blogs")
	if err != nil {
		return ListBlogsResponse{}, err
	}

	q := u.Query()
	if params.Page > 0 {
		q.Set("page", strconv.Itoa(params.Page))
	}
	if params.PageSize > 0 {
		q.Set("page_size", strconv.Itoa(params.PageSize))
	}
	u.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return ListBlogsResponse{}, err
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return ListBlogsResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return ListBlogsResponse{}, fmt.Errorf("content-service ListBlogs: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out ListBlogsResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return ListBlogsResponse{}, err
	}
	return out, nil
}

// IncrementPostView는 /api/v1/posts/{id}/view 를 호출해 조회수를 1 증가시킨다.
// 존재하지 않으면 ErrNotFound 를 반환한다.
func (c *Client) IncrementPostView(ctx context.Context, id string) error {
	u, err := url.Parse(c.baseURL)
	if err != nil {
		return err
	}
	u.Path = path.Join(u.Path, "/api/v1/posts/", id, "view")

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), nil)
	if err != nil {
		return err
	}

	resp, err := c.httpClient.Do(req)
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
		return fmt.Errorf("content-service IncrementPostView: status=%d body=%s", resp.StatusCode, string(body))
	}
}

// Health 는 content-service 의 /health 엔드포인트를 호출해 상태를 확인한다.
func (c *Client) Health(ctx context.Context) error {
	u, err := url.Parse(c.baseURL)
	if err != nil {
		return err
	}
	u.Path = path.Join(u.Path, "/health")

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return err
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("content-service Health: status=%d body=%s", resp.StatusCode, string(body))
	}
	return nil
}
