package feeder_test

import (
	"tech-letter/cmd/aggregate/feeder"
	"tech-letter/config"
	"testing"
)

func TestFetchRssFeeds(t *testing.T) {

	config.InitApp()

	var rssUrls []string
	for _, blog := range config.GetConfig().Aggregate.Blogs {
		rssUrls = append(rssUrls, blog.RSSURL)
	}

	for _, rssUrl := range rssUrls {
		items, err := feeder.FetchRssFeeds(rssUrl, 10)
		if err != nil || len(items) == 0 {
			t.Fatal(err)
		}
	}
}
