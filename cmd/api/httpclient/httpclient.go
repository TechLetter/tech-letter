package httpclient

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"

	"tech-letter/cmd/api/trace"
	"tech-letter/cmd/internal/logger"
)

// Config는 HTTP 클라이언트 공통 설정을 캡슐화한다.
// 필요 시 타임아웃, 트랜스포트, 미들웨어 등을 확장할 수 있다.
type Config struct {
	Timeout time.Duration
}

// loggingRoundTripper는 모든 아웃바운드 HTTP 호출에 대해 공통 로깅과
// X-Request-Id 헤더 트레이싱을 수행한다.
type loggingRoundTripper struct {
	inner http.RoundTripper
}

func (l *loggingRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	start := time.Now()

	ctx := req.Context()
	requestID, spanID := trace.NextSpanID(ctx)
	if requestID == "" {
		// 미들웨어 외부에서 사용된 경우를 대비한 안전장치
		requestID = req.Header.Get("X-Request-Id")
		if requestID == "" {
			requestID = trace.GenerateID()
		}
		if spanID == "" {
			spanID = "1"
		}
	}
	req.Header.Set("X-Request-Id", requestID)
	req.Header.Set("X-Span-Id", spanID)

	// 쿼리 및 요청 바디 스니펫을 로깅하기 위해 바디를 한 번 읽고 복원한다.
	query := ""
	if req.URL != nil {
		query = req.URL.RawQuery
	}
	var bodySnippet string
	if req.Body != nil {
		if bodyBytes, err := io.ReadAll(req.Body); err == nil {
			if len(bodyBytes) > 0 {
				const maxBodyLog = 1024
				if len(bodyBytes) > maxBodyLog {
					bodySnippet = string(bodyBytes[:maxBodyLog])
				} else {
					bodySnippet = string(bodyBytes)
				}
			}
			// 실제 전송을 위해 Body 를 복원한다.
			req.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
		}
	}

	resp, err := l.inner.RoundTrip(req)
	duration := time.Since(start)
	if err != nil {
		fields := logger.Fields{
			"method":     req.Method,
			"url":        req.URL.String(),
			"query":      query,
			"duration":   duration.String(),
			"request_id": requestID,
			"span_id":    spanID,
			"error":      err.Error(),
		}
		if bodySnippet != "" {
			fields["body"] = bodySnippet
		}
		logger.ErrorWithFields("httpclient request failed", fields)
		return nil, err
	}

	status := 0
	if resp != nil {
		status = resp.StatusCode
	}
	fields := logger.Fields{
		"method":     req.Method,
		"url":        req.URL.String(),
		"query":      query,
		"status":     status,
		"duration":   duration.String(),
		"request_id": requestID,
		"span_id":    spanID,
	}
	if bodySnippet != "" {
		fields["body"] = bodySnippet
	}
	logger.DebugWithFields("httpclient request success", fields)
	return resp, nil
}

// BaseClient는 공통 HTTP 클라이언트와 baseURL을 묶어두고,
// URL 생성 및 요청 생성을 도와준다.
type BaseClient struct {
	HTTPClient *http.Client
	BaseURL    string
}

// NewBaseClient는 주어진 baseURL과 기본 설정의 http.Client(logging 포함)를 사용해 BaseClient를 생성한다.
func NewBaseClient(baseURL string) *BaseClient {
	return &BaseClient{
		HTTPClient: NewDefault(),
		BaseURL:    baseURL,
	}
}

// NewBaseClientWithClient는 이미 생성된 http.Client를 사용하는 BaseClient를 생성한다.
// httpClient가 nil이면 기본 클라이언트를 사용한다.
func NewBaseClientWithClient(httpClient *http.Client, baseURL string) *BaseClient {
	if httpClient == nil {
		httpClient = NewDefault()
	}
	return &BaseClient{
		HTTPClient: httpClient,
		BaseURL:    baseURL,
	}
}

// NewRequest는 baseURL과 상대 경로, 쿼리, 바디를 사용해 새로운 HTTP 요청을 생성한다.
// relPath는 "/api/v1/..." 형태의 경로를 기대하며, 쿼리 파라미터는 반드시 query 인자로 전달해야 한다.
// relPath에 쿼리(?)가 포함된 경우 path.Join이 쿼리를 손상시키므로 에러를 반환한다.
func (c *BaseClient) NewRequest(ctx context.Context, method, relPath string, query url.Values, body io.Reader) (*http.Request, error) {
	if ctx == nil {
		ctx = context.Background()
	}
	// 방어적 검증: relPath에 쿼리가 포함되면 path.Join이 손상시키므로 사전 차단
	if strings.Contains(relPath, "?") {
		return nil, fmt.Errorf("httpclient: relPath must not contain query string (use query parameter instead): %s", relPath)
	}
	base, err := url.Parse(c.BaseURL)
	if err != nil {
		return nil, err
	}
	if relPath != "" {
		base.Path = path.Join(base.Path, relPath)
	}
	if query != nil {
		base.RawQuery = query.Encode()
	}
	return http.NewRequestWithContext(ctx, method, base.String(), body)
}

// Do는 내부 HTTP 클라이언트를 사용해 요청을 실행한다.
func (c *BaseClient) Do(req *http.Request) (*http.Response, error) {
	return c.HTTPClient.Do(req)
}

// New는 주어진 설정으로 http.Client를 생성한다.
// Timeout이 0이면 기본값 10초를 사용한다.
func New(cfg Config) *http.Client {
	timeout := cfg.Timeout
	if timeout == 0 {
		timeout = 10 * time.Second
	}

	transport := http.DefaultTransport
	return &http.Client{
		Timeout:   timeout,
		Transport: &loggingRoundTripper{inner: transport},
	}
}

// NewDefault는 공통 기본 설정(Timeout 10초)을 사용하는 http.Client를 생성한다.
func NewDefault() *http.Client {
	return New(Config{})
}
