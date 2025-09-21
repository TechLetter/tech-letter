package main

import (
	"context"
	"fmt"
	"log"
	"time"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/feeder"
	"tech-letter/models"
	"tech-letter/parser"
	"tech-letter/renderer"
	"tech-letter/summarizer"
	"tech-letter/repositories"
)

type TechBlog struct {
	Name   string
	URL    string
	IsRSS  bool
	RSSURL string
}

// truncate returns s truncated to max runes.
func truncate(s string, max int) string {
    rs := []rune(s)
    if len(rs) <= max {
        return s
    }
    return string(rs[:max])
}

func main() {
	config.InitApp()

	// Initialize MongoDB
	ctx := context.Background()
	if err := db.Init(ctx); err != nil {
		log.Fatal("failed to initialize MongoDB:", err)
	}

	blogs := []TechBlog{
		{
			Name:   "카카오",
			URL:    "https://tech.kakao.com/blog",
			RSSURL: "https://tech.kakao.com/feed/",
		},
		{
			Name:   "카카오 페이",
			URL:    "https://tech.kakaopay.com",
			RSSURL: "https://tech.kakaopay.com/rss",
		},
		{
			Name:   "네이버",
			URL:    "https://d2.naver.com/home",
			RSSURL: "https://d2.naver.com/d2.atom",
		},
		{
			Name:   "우아한 형제들",
			URL:    "https://techblog.woowahan.com",
			RSSURL: "https://techblog.woowahan.com/feed/",
		},
		{
			Name:   "당근마켓",
			URL:    "https://medium.com/daangn",
			RSSURL: "https://medium.com/feed/daangn",
		},
		{
			Name:   "리멤버",
			URL:    "https://tech.remember.co.kr",
			RSSURL: "https://tech.remember.co.kr/feed",
		},
	}

	// Upsert blogs into MongoDB
	blogRepo := repositories.NewBlogRepository(db.Database())
	postRepo := repositories.NewPostRepository(db.Database())
	postHTMLRepo := repositories.NewPostHTMLRepository(db.Database())
	postTextRepo := repositories.NewPostTextRepository(db.Database())
	aiLogRepo := repositories.NewAILogRepository(db.Database())
	for _, b := range blogs {
		mb := &models.Blog{
			Name:     b.Name,
			URL:      b.URL,
			RSSURL:   b.RSSURL,
			BlogType: "company",
		}
		if _, err := blogRepo.UpsertByRSSURL(ctx, mb); err != nil {
			log.Printf("failed to upsert blog %s: %v", b.Name, err)
		}
	}

	for _, blog := range blogs {
		// Find blog doc to get BlogID
		blogDoc, err := blogRepo.GetByRSSURL(ctx, blog.RSSURL)
		if err != nil {
			log.Printf("skip fetching posts for %s: failed to find blog doc: %v", blog.Name, err)
			continue
		}

		feed, err := feeder.FetchRssFeeds(blog.RSSURL, 10)
		if err != nil {
			log.Fatal(err)
		}

		for i, item := range feed {
			fmt.Printf("%s \t%d. 제목: %s\n링크: %s\n게시일: %s\n\n", blog.Name, i, item.Title, item.Link, item.PublishedAt)
			// Upsert into posts
			p := &models.Post{
				BlogID:   blogDoc.ID,
				BlogName: blogDoc.Name,
				Title:    item.Title,
				Link:     item.Link,
			}
			if !item.PublishedAt.IsZero() {
				p.PublishedAt = item.PublishedAt
			}
			if _, err := postRepo.UpsertByBlogAndLink(ctx, p); err != nil {
				log.Printf("failed to upsert post (blog=%s, title=%s): %v", blog.Name, item.Title, err)
				continue
			}

			// Load saved post to get its ID
			saved, err := postRepo.FindByBlogAndLink(ctx, blogDoc.ID, item.Link)
			if err != nil {
				log.Printf("failed to reload post (blog=%s, link=%s): %v", blog.Name, item.Link, err)
				continue
			}

			// Prepare flags from existing doc
			flags := saved.Status

			// 1) HTML 단계: 이미 수집되어 있으면 재사용, 아니면 렌더링 후 저장
			var htmlStr string
			if flags.HTMLFetched {
				if htmlDoc, err := postHTMLRepo.FindByPostID(ctx, saved.ID); err == nil {
					htmlStr = htmlDoc.RawHTML
				} else {
					// 플래그와 데이터 불일치 시 재수집 시도
					start := time.Now()
					htmlStr, err = renderer.RenderHTML(item.Link)
					dur := time.Since(start)
					if err == nil {
						_, _ = postHTMLRepo.UpsertByPost(ctx, &models.PostHTML{
							PostID:          saved.ID,
							RawHTML:         htmlStr,
							FetchedAt:       time.Now(),
							FetchDurationMs: dur.Milliseconds(),
							HTMLSizeBytes:   int64(len([]byte(htmlStr))),
							BlogName:        blogDoc.Name,
							PostTitle:       item.Title,
						})
					}
				}
			} else {
				start := time.Now()
				var err error
				htmlStr, err = renderer.RenderHTML(item.Link)
				dur := time.Since(start)
				if err != nil {
					log.Printf("failed to render HTML: %v", err)
					continue
				}
				if _, err := postHTMLRepo.UpsertByPost(ctx, &models.PostHTML{
					PostID:          saved.ID,
					RawHTML:         htmlStr,
					FetchedAt:       time.Now(),
					FetchDurationMs: dur.Milliseconds(),
					HTMLSizeBytes:   int64(len([]byte(htmlStr))),
					BlogName:        blogDoc.Name,
					PostTitle:       item.Title,
				}); err != nil {
					log.Printf("failed to upsert post_html: %v", err)
					continue
				}
				flags.HTMLFetched = true
				_ = postRepo.UpdateStatusFlags(ctx, saved.ID, flags)
			}

			// 2) TEXT 단계: 이미 파싱되어 있으면 재사용, 아니면 파싱 후 저장
			var plain string
			if flags.TextParsed {
				if txt, err := postTextRepo.FindByPostID(ctx, saved.ID); err == nil {
					plain = txt.PlainText
				} else {
					parsed, err := parser.ParseArticleOfHTML(htmlStr)
					if err == nil {
						plain = parsed.PlainTextContent
						_, _ = postTextRepo.UpsertByPost(ctx, &models.PostText{
							PostID:    saved.ID,
							PlainText: plain,
							ParsedAt:  time.Now(),
							WordCount: len([]rune(plain)),
							BlogName:  blogDoc.Name,
							PostTitle: item.Title,
						})
					}
				}
			} else {
				parsed, err := parser.ParseArticleOfHTML(htmlStr)
				if err != nil {
					log.Printf("failed to parse HTML: %v", err)
					continue
				}
				plain = parsed.PlainTextContent
				if _, err := postTextRepo.UpsertByPost(ctx, &models.PostText{
					PostID:    saved.ID,
					PlainText: plain,
					ParsedAt:  time.Now(),
					WordCount: len([]rune(plain)),
					BlogName:  blogDoc.Name,
					PostTitle: item.Title,
				}); err != nil {
					log.Printf("failed to upsert post_text: %v", err)
					continue
				}
				flags.TextParsed = true
				_ = postRepo.UpdateStatusFlags(ctx, saved.ID, flags)
			}

			// 3) AI SUMMARY 단계: 이미 요약 완료면 스킵, 아니면 호출 후 저장
			if !flags.AISummarized {
				sumStart := time.Now()
				summary, err := summarizer.SummarizeText(plain)
				sumDur := time.Since(sumStart)
				if err != nil {
					log.Printf("failed to summarize: %v", err)
					continue
				}
				info := models.AIGeneratedInfo{
					Categories:      summary.Categories,
					Tags:            summary.Tags,
					SummaryShort:    summary.SummaryShort,
					SummaryLong:     summary.SummaryLong,
					ModelName:       config.GetConfig().GeminiModel,
					ConfidenceScore: 0,
					GeneratedAt:     time.Now(),
				}
				if err := postRepo.UpdateAIGeneratedInfo(ctx, saved.ID, info, summary.SummaryShort); err != nil {
					log.Printf("failed to update ai_generated_info: %v", err)
				}
				_, _ = aiLogRepo.Insert(ctx, models.AILog{
					PostID:           saved.ID,
					Model:            config.GetConfig().GeminiModel,
					PromptTokens:     0,
					CompletionTokens: 0,
					TotalTokens:      0,
					DurationMs:       sumDur.Milliseconds(),
					Success:          true,
					ResponseExcerpt:  truncate(summary.SummaryLong, 200),
					RequestedAt:      sumStart,
					CompletedAt:      time.Now(),
				})
				flags.AISummarized = true
				_ = postRepo.UpdateStatusFlags(ctx, saved.ID, flags)
			}
		}
	}
}
