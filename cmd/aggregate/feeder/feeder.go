package feeder

import (
	"bytes"
	"crypto/tls"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"time"

	"github.com/mmcdole/gofeed"
)

// RssFeedItem 구조체는 가정하고 작성합니다.
type RssFeedItem struct {
	Title       string
	Link        string
	PublishedAt time.Time
}

const FEEDER_TIMEOUT = 30 * time.Second

// rssUserAgent 는 RSS 피드를 요청할 때 사용할 브라우저 유사 User-Agent 이다.
// 일부 블로그(특히 CDN/보안 프록시 뒤에 있는 경우)는 기본 Go HTTP 클라이언트 UA를 차단한다.
const rssUserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"

func FetchRssFeeds(rssUrl string, limit int) ([]RssFeedItem, error) {
	// 1. 리다이렉트 정책을 포함한 클라이언트 설정
	httpClient := &http.Client{
		Timeout: FEEDER_TIMEOUT,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		},
		// 리다이렉트 시 헤더 유지를 위해 필요할 수 있음 (Go 기본 동작은 헤더가 초기화될 수 있음)
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 10 {
				return fmt.Errorf("stopped after 10 redirects")
			}
			// 리다이렉트 시 이전 요청의 User-Agent를 유지
			req.Header.Set("User-Agent", rssUserAgent)
			return nil
		},
	}

	// 2. 파서 생성 (fp.Client 설정은 여기서 불필요하므로 제거)
	fp := gofeed.NewParser()

	req, err := http.NewRequest(http.MethodGet, rssUrl, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create RSS request: %w", err)
	}

	// 3. 헤더 보강: WAF 우회를 위해 더 많은 브라우저 헤더 추가
	req.Header.Set("User-Agent", rssUserAgent)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.9")
	req.Header.Set("Referer", "https://www.google.com/") // 리퍼러 추가
	req.Header.Set("Upgrade-Insecure-Requests", "1")
	req.Header.Set("Cache-Control", "max-age=0")
	req.Header.Set("Connection", "keep-alive")

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	// 4. 에러 디버깅을 위한 상세 처리
	if resp.StatusCode != http.StatusOK {
		// 본문 내용을 조금 읽어서 로그에 찍어보면 원인 파악에 도움이 됨
		bodySample, _ := io.ReadAll(io.LimitReader(resp.Body, 500))
		return nil, fmt.Errorf("failed to fetch RSS feed: status code %d, url: %s, body: %s", resp.StatusCode, rssUrl, string(bodySample))
	}

	// 5. 제어 문자 제거 (기존 로직 유지)
	cleanedReader, err := cleanControlCharacters(resp.Body)
	if err != nil {
		return nil, err
	}

	// 6. 파싱
	feed, err := fp.Parse(cleanedReader)
	if err != nil {
		return nil, fmt.Errorf("failed to parse RSS feed: %w", err)
	}

	var items []RssFeedItem
	for _, item := range feed.Items {
		var published time.Time
		if item.PublishedParsed != nil {
			published = *item.PublishedParsed
		} else if item.UpdatedParsed != nil {
			published = *item.UpdatedParsed
		}

		items = append(items, RssFeedItem{
			Title:       item.Title,
			Link:        item.Link,
			PublishedAt: published,
		})
	}

	if limit > 0 && len(items) > limit {
		items = items[:limit]
	}

	return items, nil
}

// XML에서 허용되지 않는 모든 제어 문자 범위입니다 (0x00부터 0x1F까지 중 탭, LF, CR 제외).
// U+001B (\x1B)와 U+001C (\x1C)는 이 정규식에 포함됩니다.
var invalidControlCharRegex = regexp.MustCompile(`[\x00-\x08\x0B\x0C\x0E-\x1F]`)

func cleanControlCharacters(r io.Reader) (io.Reader, error) {
	bodyBytes, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("failed to read body for cleaning: %w", err)
	}

	cleanedBytes := invalidControlCharRegex.ReplaceAll(bodyBytes, []byte(""))

	return bytes.NewReader(cleanedBytes), nil
}
