package feeder_test

import (
	"testing"

	"tech-letter/feeder"
)

func TestFetchRssFeeds(t *testing.T) {
	items, err := feeder.FetchRssFeeds("https://tech.kakao.com/feed/", 10)
	if err != nil {
		t.Fatal(err)
	}
	t.Log(items)
}
