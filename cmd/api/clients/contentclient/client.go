package contentclient

import (
	"bytes"
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

	"tech-letter/cmd/api/httpclient"
)

// Client는 Python content-service HTTP API를 호출하는 얇은 클라이언트다.
//
// - 인증/유저 로직은 전혀 알지 않고, 순수하게 콘텐츠 데이터만 가져온다.
// - API Gateway(Go cmd/api)에서 이 클라이언트를 사용해 DTO를 조합한다.
//
// baseURL 예: http://content_service:8001

type Client struct {
	base *httpclient.BaseClient
}

// GetPostsBatch는 POST /api/v1/posts/batch 엔드포인트를 호출해
// 주어진 ID 목록에 해당하는 포스트들을 한 번에 조회한다.
func (c *Client) GetPostsBatch(ctx context.Context, ids []string) (ListPostsResponse, error) {
	body := struct {
		IDs []string `json:"ids"`
	}{IDs: ids}

	buf, err := json.Marshal(body)
	if err != nil {
		return ListPostsResponse{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/posts/batch", nil, bytes.NewReader(buf))
	if err != nil {
		return ListPostsResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return ListPostsResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return ListPostsResponse{}, fmt.Errorf("content-service GetPostsBatch: status=%d body=%s", resp.StatusCode, string(b))
	}

	var out ListPostsResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return ListPostsResponse{}, err
	}
	return out, nil
}

var ErrNotFound = errors.New("resource not found")

type HTTPError struct {
	Operation  string
	StatusCode int
	Body       string
}

func (e *HTTPError) Error() string {
	return fmt.Sprintf("%s: status=%d body=%s", e.Operation, e.StatusCode, e.Body)
}

func IsStatus(err error, statusCode int) bool {
	var httpErr *HTTPError
	return errors.As(err, &httpErr) && httpErr.StatusCode == statusCode
}

func newHTTPError(operation string, resp *http.Response) error {
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
	return &HTTPError{
		Operation:  operation,
		StatusCode: resp.StatusCode,
		Body:       string(body),
	}
}

func New() *Client {
	base := os.Getenv("CONTENT_SERVICE_BASE_URL")
	if base == "" {
		base = "http://content_service:8001"
	}

	return &Client{
		base: httpclient.NewBaseClient(base),
	}
}

// -------------------- Posts --------------------

type ListPostsParams struct {
	Page          int
	PageSize      int
	Categories    []string
	Tags          []string
	BlogID        string
	BlogName      string
	PublishedFrom *time.Time
	PublishedTo   *time.Time
	// Status Filters (추후 DocumentEmbedded 등 추가 가능)
	StatusAISummarized *bool
	StatusEmbedded     *bool
}

type ListPostsResponse struct {
	Total    int        `json:"total"`
	Items    []PostItem `json:"items"`
	Page     int        `json:"page"`
	PageSize int        `json:"page_size"`
}

type PostItem struct {
	ID           string             `json:"id"`
	CreatedAt    time.Time          `json:"created_at"`
	UpdatedAt    time.Time          `json:"updated_at"`
	ViewCount    int                `json:"view_count"`
	BlogID       string             `json:"blog_id"`
	BlogName     string             `json:"blog_name"`
	Title        string             `json:"title"`
	Link         string             `json:"link"`
	PublishedAt  time.Time          `json:"published_at"`
	ThumbnailURL string             `json:"thumbnail_url"`
	Status       StatusFlags        `json:"status"`
	AISummary    *AISummary         `json:"aisummary"`
	Embedding    *EmbeddingMetadata `json:"embedding"`
}

type StatusFlags struct {
	AISummarized bool `json:"ai_summarized"`
	Embedded     bool `json:"embedded"`
}

type AISummary struct {
	Categories  []string  `json:"categories"`
	Tags        []string  `json:"tags"`
	Summary     string    `json:"summary"`
	ModelName   string    `json:"model_name"`
	GeneratedAt time.Time `json:"generated_at"`
}

type EmbeddingMetadata struct {
	ModelName       string    `json:"model_name"`
	CollectionName  string    `json:"collection_name"`
	VectorDimension int       `json:"vector_dimension"`
	ChunkCount      int       `json:"chunk_count"`
	EmbeddedAt      time.Time `json:"embedded_at"`
}

func (c *Client) ListPosts(ctx context.Context, params ListPostsParams) (ListPostsResponse, error) {
	q := url.Values{}
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
	if params.PublishedFrom != nil {
		q.Set("published_from", params.PublishedFrom.UTC().Format(time.RFC3339Nano))
	}
	if params.PublishedTo != nil {
		q.Set("published_to", params.PublishedTo.UTC().Format(time.RFC3339Nano))
	}
	if params.StatusAISummarized != nil {
		q.Set("status_ai_summarized", strconv.FormatBool(*params.StatusAISummarized))
	}
	if params.StatusEmbedded != nil {
		q.Set("status_embedded", strconv.FormatBool(*params.StatusEmbedded))
	}
	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/posts", q, nil)
	if err != nil {
		return ListPostsResponse{}, err
	}

	resp, err := c.base.Do(req)
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
	relPath := path.Join("/api/v1/posts", id)
	req, err := c.base.NewRequest(ctx, http.MethodGet, relPath, nil, nil)
	if err != nil {
		return PostItem{}, err
	}

	resp, err := c.base.Do(req)
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
	Page            int
	PageSize        int
	IncludeInactive bool
}

type ListBlogsResponse struct {
	Total    int        `json:"total"`
	Items    []BlogItem `json:"items"`
	Page     int        `json:"page"`
	PageSize int        `json:"page_size"`
}

type BlogItem struct {
	ID             string     `json:"id"`
	CreatedAt      time.Time  `json:"created_at"`
	UpdatedAt      time.Time  `json:"updated_at"`
	Name           string     `json:"name"`
	URL            string     `json:"url"`
	RSSURL         string     `json:"rss_url"`
	BlogType       string     `json:"blog_type"`
	IsActive       bool       `json:"is_active"`
	LastFetchedAt  *time.Time `json:"last_fetched_at"`
	LastFetchError *string    `json:"last_fetch_error"`
	PostCount      int        `json:"post_count"`
}

func (c *Client) ListBlogs(ctx context.Context, params ListBlogsParams) (ListBlogsResponse, error) {
	q := url.Values{}
	if params.Page > 0 {
		q.Set("page", strconv.Itoa(params.Page))
	}
	if params.PageSize > 0 {
		q.Set("page_size", strconv.Itoa(params.PageSize))
	}
	if params.IncludeInactive {
		q.Set("include_inactive", "true")
	}
	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/blogs", q, nil)
	if err != nil {
		return ListBlogsResponse{}, err
	}

	resp, err := c.base.Do(req)
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

type BlogMutationRequest struct {
	Name     string `json:"name"`
	URL      string `json:"url"`
	RSSURL   string `json:"rss_url"`
	BlogType string `json:"blog_type"`
	IsActive bool   `json:"is_active"`
}

type DeleteBlogResponse struct {
	OK           bool `json:"ok"`
	DeletedPosts int  `json:"deleted_posts"`
}

func (c *Client) CreateBlog(ctx context.Context, body BlogMutationRequest) (BlogItem, error) {
	buf, err := json.Marshal(body)
	if err != nil {
		return BlogItem{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/blogs", nil, bytes.NewReader(buf))
	if err != nil {
		return BlogItem{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return BlogItem{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		return BlogItem{}, newHTTPError("content-service CreateBlog", resp)
	}

	var out BlogItem
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return BlogItem{}, err
	}
	return out, nil
}

func (c *Client) UpdateBlog(ctx context.Context, id string, body BlogMutationRequest) (BlogItem, error) {
	buf, err := json.Marshal(body)
	if err != nil {
		return BlogItem{}, err
	}

	relPath := path.Join("/api/v1/blogs", id)
	req, err := c.base.NewRequest(ctx, http.MethodPut, relPath, nil, bytes.NewReader(buf))
	if err != nil {
		return BlogItem{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return BlogItem{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return BlogItem{}, newHTTPError("content-service UpdateBlog", resp)
	}

	var out BlogItem
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return BlogItem{}, err
	}
	return out, nil
}

func (c *Client) DeleteBlog(ctx context.Context, id string, deletePosts bool) (DeleteBlogResponse, error) {
	q := url.Values{}
	q.Set("delete_posts", strconv.FormatBool(deletePosts))

	relPath := path.Join("/api/v1/blogs", id)
	req, err := c.base.NewRequest(ctx, http.MethodDelete, relPath, q, nil)
	if err != nil {
		return DeleteBlogResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return DeleteBlogResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return DeleteBlogResponse{}, newHTTPError("content-service DeleteBlog", resp)
	}

	var out DeleteBlogResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return DeleteBlogResponse{}, err
	}
	return out, nil
}

// IncrementPostView는 /api/v1/posts/{id}/view 를 호출해 조회수를 1 증가시킨다.
// 존재하지 않으면 ErrNotFound 를 반환한다.
func (c *Client) IncrementPostView(ctx context.Context, id string) error {
	relPath := path.Join("/api/v1/posts", id, "view")
	req, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, nil)
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
		return fmt.Errorf("content-service IncrementPostView: status=%d body=%s", resp.StatusCode, string(body))
	}
}

// Health 는 content-service 의 /health 엔드포인트를 호출해 상태를 확인한다.
func (c *Client) Health(ctx context.Context) error {
	req, err := c.base.NewRequest(ctx, http.MethodGet, "/health", nil, nil)
	if err != nil {
		return err
	}

	resp, err := c.base.Do(req)
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

// -------------------- Filters --------------------

type FilterParams struct {
	BlogID     string
	Categories []string
	Tags       []string
}

type FilterItem struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

type CategoryFilterResponse struct {
	Items []FilterItem `json:"items"`
}

type TagFilterResponse struct {
	Items []FilterItem `json:"items"`
}

type BlogFilterItem struct {
	ID    string `json:"id"`
	Name  string `json:"name"`
	Count int    `json:"count"`
}

type BlogFilterResponse struct {
	Items []BlogFilterItem `json:"items"`
}

// GetCategoryFilters retrieves category filter statistics from content service
func (c *Client) GetCategoryFilters(ctx context.Context, params FilterParams) (CategoryFilterResponse, error) {
	q := url.Values{}
	if params.BlogID != "" {
		q.Set("blog_id", params.BlogID)
	}
	for _, tag := range params.Tags {
		q.Add("tags", tag)
	}
	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/filters/categories", q, nil)
	if err != nil {
		return CategoryFilterResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return CategoryFilterResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return CategoryFilterResponse{}, fmt.Errorf("content-service GetCategoryFilters: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out CategoryFilterResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return CategoryFilterResponse{}, err
	}
	return out, nil
}

// GetTagFilters retrieves tag filter statistics from content service
func (c *Client) GetTagFilters(ctx context.Context, params FilterParams) (TagFilterResponse, error) {
	q := url.Values{}
	if params.BlogID != "" {
		q.Set("blog_id", params.BlogID)
	}
	for _, cat := range params.Categories {
		q.Add("categories", cat)
	}
	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/filters/tags", q, nil)
	if err != nil {
		return TagFilterResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return TagFilterResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return TagFilterResponse{}, fmt.Errorf("content-service GetTagFilters: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out TagFilterResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return TagFilterResponse{}, err
	}
	return out, nil
}

// GetBlogFilters retrieves blog filter statistics from content service
func (c *Client) GetBlogFilters(ctx context.Context, params FilterParams) (BlogFilterResponse, error) {
	q := url.Values{}
	for _, cat := range params.Categories {
		q.Add("categories", cat)
	}
	for _, tag := range params.Tags {
		q.Add("tags", tag)
	}
	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/filters/blogs", q, nil)
	if err != nil {
		return BlogFilterResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return BlogFilterResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return BlogFilterResponse{}, fmt.Errorf("content-service GetBlogFilters: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out BlogFilterResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return BlogFilterResponse{}, err
	}
	return out, nil
}

// -------------------- Trends --------------------

type TrendParams struct {
	Period string
	Limit  int
}

type TrendSeriesParams struct {
	Tags     []string
	Period   string
	Interval string
}

type TrendPostsParams struct {
	Tags     []string
	Period   string
	Page     int
	PageSize int
}

type RisingTrendPeriod struct {
	From         time.Time `json:"from"`
	To           time.Time `json:"to"`
	PreviousFrom time.Time `json:"previous_from"`
	PreviousTo   time.Time `json:"previous_to"`
}

type RisingTagItem struct {
	Tag           string   `json:"tag"`
	CurrentCount  int      `json:"current_count"`
	PreviousCount int      `json:"previous_count"`
	Delta         int      `json:"delta"`
	GrowthRate    *float64 `json:"growth_rate"`
}

type RisingTagsResponse struct {
	Period RisingTrendPeriod `json:"period"`
	Items  []RisingTagItem   `json:"items"`
}

type SeriesTrendPeriod struct {
	From     time.Time `json:"from"`
	To       time.Time `json:"to"`
	Interval string    `json:"interval"`
}

type TrendSeriesPoint struct {
	Bucket    time.Time `json:"bucket"`
	PostCount int       `json:"post_count"`
	BlogCount int       `json:"blog_count"`
}

type TrendSeriesItem struct {
	Tag    string             `json:"tag"`
	Points []TrendSeriesPoint `json:"points"`
}

type TrendSeriesResponse struct {
	Period SeriesTrendPeriod `json:"period"`
	Series []TrendSeriesItem `json:"series"`
}

func (c *Client) GetRisingTags(ctx context.Context, params TrendParams) (RisingTagsResponse, error) {
	q := url.Values{}
	if params.Period != "" {
		q.Set("period", params.Period)
	}
	if params.Limit > 0 {
		q.Set("limit", strconv.Itoa(params.Limit))
	}

	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/trends/rising", q, nil)
	if err != nil {
		return RisingTagsResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return RisingTagsResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return RisingTagsResponse{}, fmt.Errorf("content-service GetRisingTags: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out RisingTagsResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return RisingTagsResponse{}, err
	}
	return out, nil
}

func (c *Client) GetTrendSeries(ctx context.Context, params TrendSeriesParams) (TrendSeriesResponse, error) {
	q := url.Values{}
	for _, tag := range params.Tags {
		q.Add("tags", tag)
	}
	if params.Period != "" {
		q.Set("period", params.Period)
	}
	if params.Interval != "" {
		q.Set("interval", params.Interval)
	}

	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/trends/series", q, nil)
	if err != nil {
		return TrendSeriesResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return TrendSeriesResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return TrendSeriesResponse{}, fmt.Errorf("content-service GetTrendSeries: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out TrendSeriesResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return TrendSeriesResponse{}, err
	}
	return out, nil
}

func (c *Client) ListTrendPosts(ctx context.Context, params TrendPostsParams) (ListPostsResponse, error) {
	q := url.Values{}
	for _, tag := range params.Tags {
		q.Add("tags", tag)
	}
	if params.Period != "" {
		q.Set("period", params.Period)
	}
	if params.Page > 0 {
		q.Set("page", strconv.Itoa(params.Page))
	}
	if params.PageSize > 0 {
		q.Set("page_size", strconv.Itoa(params.PageSize))
	}

	req, err := c.base.NewRequest(ctx, http.MethodGet, "/api/v1/trends/posts", q, nil)
	if err != nil {
		return ListPostsResponse{}, err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return ListPostsResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return ListPostsResponse{}, fmt.Errorf("content-service ListTrendPosts: status=%d body=%s", resp.StatusCode, string(body))
	}

	var out ListPostsResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return ListPostsResponse{}, err
	}
	return out, nil
}

// -------------------- Admin Methods --------------------

type CreatePostRequest struct {
	Title  string `json:"title"`
	Link   string `json:"link"`
	BlogID string `json:"blog_id"`
}

type CreatePostResponse struct {
	ID    string `json:"id"`
	Title string `json:"title"`
}

func (c *Client) CreatePost(ctx context.Context, title, link, blogID string) (CreatePostResponse, error) {
	body := CreatePostRequest{Title: title, Link: link, BlogID: blogID}
	buf, err := json.Marshal(body)
	if err != nil {
		return CreatePostResponse{}, err
	}

	req, err := c.base.NewRequest(ctx, http.MethodPost, "/api/v1/posts", nil, bytes.NewReader(buf))
	if err != nil {
		return CreatePostResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.base.Do(req)
	if err != nil {
		return CreatePostResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return CreatePostResponse{}, fmt.Errorf("content-service CreatePost: status=%d body=%s", resp.StatusCode, string(b))
	}

	var out CreatePostResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return CreatePostResponse{}, err
	}
	return out, nil
}

func (c *Client) DeletePost(ctx context.Context, id string) error {
	relPath := path.Join("/api/v1/posts", id)
	req, err := c.base.NewRequest(ctx, http.MethodDelete, relPath, nil, nil)
	if err != nil {
		return err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("content-service DeletePost: status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

func (c *Client) TriggerSummary(ctx context.Context, id string) error {
	relPath := path.Join("/api/v1/posts", id, "summarize")
	req, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, nil)
	if err != nil {
		return err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("content-service TriggerSummary: status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

func (c *Client) TriggerEmbedding(ctx context.Context, id string) error {
	relPath := path.Join("/api/v1/posts", id, "embed")
	req, err := c.base.NewRequest(ctx, http.MethodPost, relPath, nil, nil)
	if err != nil {
		return err
	}

	resp, err := c.base.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("content-service TriggerEmbedding: status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}
