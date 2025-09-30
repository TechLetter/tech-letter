package feeder_test

import (
	"testing"

	"tech-letter/feeder"
)

func TestFetchRssFeeds(t *testing.T) {

	var rssUrls = []string{
		"https://tech.kakao.com/feed/",
		"https://medium.com/feed/pinkfong",
	}

	for _, rssUrl := range rssUrls {
		items, err := feeder.FetchRssFeeds(rssUrl, 10)
		if err != nil || len(items) == 0 {
			t.Fatal(err)
		}
	}
}
