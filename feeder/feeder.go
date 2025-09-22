package feeder

import (
	"crypto/tls"
	"net/http"
	"time"

	"github.com/mmcdole/gofeed"
)

type RssFeedItem struct {
	Title       string
	Link        string
	PublishedAt time.Time
}

// FetchRssFeeds fetches RSS feeds from the given URL.
// If limit is greater than 0, it returns only the first limit items.
func FetchRssFeeds(rssUrl string, limit int) ([]RssFeedItem, error) {
	httpClient := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true}, // SSL 인증서 검증을 건너뛰는 설정 , ex) 우아한 형제들
		},
	}

	fp := gofeed.NewParser()
	fp.Client = httpClient

	feed, err := fp.ParseURL(rssUrl)
	if err != nil {
		return nil, err
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
