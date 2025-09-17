package main

import (
	"fmt"
	"log"

	"github.com/mmcdole/gofeed"
)

type TechBlog struct {
	Name string
	URL string
	IsRSS bool
	RSSURL string
}

func main() {
	blogs := []TechBlog{
		{
			Name: "카카오",
			URL: "https://tech.kakao.com/blog",
			IsRSS: true,
			RSSURL: "https://tech.kakao.com/feed/",
		},
		{
			Name: "카카오 페이",
			URL: "https://tech.kakaopay.com",
			IsRSS: true,
			RSSURL: "https://tech.kakaopay.com/rss",
		},
		{
			Name: "네이버",
			URL: "https://d2.naver.com/home",
			IsRSS: true,
			RSSURL: "https://d2.naver.com/d2.atom",
		},
		{
			Name: "우아한 형제들",
			URL: "https://techblog.woowahan.com",
			IsRSS: true,
			RSSURL: "https://techblog.woowahan.com/feed/",
		},
		{
			Name: "당근마켓",
			URL: "https://medium.com/daangn",
			IsRSS: true,
			RSSURL: "https://medium.com/feed/daangn",
		},
		{
			Name: "리멤버",
			URL: "https://tech.remember.co.kr",
			IsRSS: true,
			RSSURL: "https://tech.remember.co.kr/feed",
		},
	}

	for _, blog := range blogs {
		fp := gofeed.NewParser()
		feed, err := fp.ParseURL(blog.RSSURL)
		if err != nil {
			log.Fatal(err)
		}

		for i, item := range feed.Items {
			if i >= 3000 {
				break
			}
			fmt.Println(blog.Name)
			fmt.Printf("%d. 제목: %s\n링크: %s\n게시일: %s\n\n", i, item.Title, item.Link, item.Published)
		}
	}
}
