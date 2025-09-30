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

func FetchRssFeeds(rssUrl string, limit int) ([]RssFeedItem, error) {
	httpClient := &http.Client{
		Timeout: FEEDER_TIMEOUT,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		},
	}

	fp := gofeed.NewParser()
	fp.Client = httpClient

	resp, err := httpClient.Get(rssUrl)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to fetch RSS feed: status code %d", resp.StatusCode)
	}

	cleanedReader, err := cleanControlCharacters(resp.Body)
	if err != nil {
		return nil, err
	}

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
