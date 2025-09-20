package main

import (
	"fmt"
	"log"
	"os"
	"tech-letter/config"
	"tech-letter/parser"
	"tech-letter/renderer"
	"tech-letter/summarizer"
	"time"

	"github.com/mmcdole/gofeed"
)

type TechBlog struct {
	Name   string
	URL    string
	IsRSS  bool
	RSSURL string
}

func main() {
	config.InitApp()

	blogs := []TechBlog{
		{
			Name:   "카카오",
			URL:    "https://tech.kakao.com/blog",
			IsRSS:  true,
			RSSURL: "https://tech.kakao.com/feed/",
		},
		{
			Name:   "카카오 페이",
			URL:    "https://tech.kakaopay.com",
			IsRSS:  true,
			RSSURL: "https://tech.kakaopay.com/rss",
		},
		{
			Name:   "네이버",
			URL:    "https://d2.naver.com/home",
			IsRSS:  true,
			RSSURL: "https://d2.naver.com/d2.atom",
		},
		{
			Name:   "우아한 형제들",
			URL:    "https://techblog.woowahan.com",
			IsRSS:  true,
			RSSURL: "https://techblog.woowahan.com/feed/",
		},
		{
			Name:   "당근마켓",
			URL:    "https://medium.com/daangn",
			IsRSS:  true,
			RSSURL: "https://medium.com/feed/daangn",
		},
		{
			Name:   "리멤버",
			URL:    "https://tech.remember.co.kr",
			IsRSS:  true,
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
			if i >= 1 {
				break
			}
			fmt.Printf("%s \t%d. 제목: %s\n링크: %s\n게시일: %s\n\n", blog.Name, i, item.Title, item.Link, item.Published)
			now := time.Now()
			htmlStr, err := renderer.RenderHTML(item.Link)
			if err != nil {
				log.Fatal(err)
			}
			log.Println("HTML rendering time:", time.Since(now))

			article, err := parser.ParseArticleOfHTML(htmlStr)
			if err != nil {
				log.Fatal(err)
			}
			log.Println("HTML parsing time:", time.Since(now))

			summary, err := summarizer.SummarizeText(article.PlainTextContent)
			if err != nil {
				log.Fatal(err)
			}
			log.Println("Summarizing time:", time.Since(now))

			if summary.IsFailure {
				err := os.WriteFile(fmt.Sprintf("failures-%s.txt", blog.Name), []byte(htmlStr), 0644)
				if err != nil {
					log.Fatal(err)
				}
				continue
			}

			fmt.Println(summary.SummaryShort)

			fmt.Print("\n\n\n\n")

		}
	}
}
