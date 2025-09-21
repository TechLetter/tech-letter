package main

import (
	"context"
	"log"
	"time"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/feeder"
	"tech-letter/models"
	"tech-letter/parser"
	"tech-letter/renderer"
	"tech-letter/repositories"
	"tech-letter/summarizer"
)

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

	ctx := context.Background()
	if err := db.Init(ctx); err != nil {
		log.Fatal("failed to initialize MongoDB:", err)
	}

	// 첫 실행은 즉시 1회 수행
	if err := runOnce(ctx); err != nil {
		log.Printf("aggregate runOnce error: %v", err)
	}

	// Asia/Seoul 기준 자정마다 수행
	loc, err := time.LoadLocation("Asia/Seoul")
	if err != nil {
		loc = time.Local
	}
	for {
		now := time.Now().In(loc)
		nextMidnight := time.Date(now.Year(), now.Month(), now.Day()+1, 0, 0, 0, 0, loc)
		sleepDur := time.Until(nextMidnight)
		if sleepDur <= 0 {
			sleepDur = time.Minute // fallback
		}
		log.Printf("aggregate sleeping until %s (%s)", nextMidnight.Format(time.RFC3339), loc)
		time.Sleep(sleepDur)
		if err := runOnce(ctx); err != nil {
			log.Printf("aggregate runOnce error: %v", err)
		}
	}
}

// runOnce executes one full aggregation cycle for all configured blogs.
func runOnce(ctx context.Context) error {
	blogRepo := repositories.NewBlogRepository(db.Database())
	postRepo := repositories.NewPostRepository(db.Database())
	postHTMLRepo := repositories.NewPostHTMLRepository(db.Database())
	postTextRepo := repositories.NewPostTextRepository(db.Database())
	aiLogRepo := repositories.NewAILogRepository(db.Database())

	cfgBlogs := config.GetConfig().Blogs
	if len(cfgBlogs) == 0 {
		log.Printf("no blogs configured in config.yaml (key: blogs)")
		return nil
	}

	for _, b := range cfgBlogs {
		mb := &models.Blog{
			Name:     b.Name,
			URL:      b.URL,
			RSSURL:   b.RSSURL,
			BlogType: func() string { if b.BlogType != "" { return b.BlogType }; return "company" }(),
		}
		if _, err := blogRepo.UpsertByRSSURL(ctx, mb); err != nil {
			log.Printf("failed to upsert blog %s: %v", b.Name, err)
		}
	}

	for _, blog := range cfgBlogs {
		// Find blog doc to get BlogID
		blogDoc, err := blogRepo.GetByRSSURL(ctx, blog.RSSURL)
		if err != nil {
			log.Printf("skip fetching posts for %s: failed to find blog doc: %v", blog.Name, err)
			continue
		}

		feed, err := feeder.FetchRssFeeds(blog.RSSURL, 10)
		if err != nil {
			log.Printf("fetch rss error for %s: %v", blog.Name, err)
			continue
		}

		for _, item := range feed {
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
					// 썸네일이 비어있다면 HTML에서 추출만 수행해 채움
					if saved.ThumbnailURL == "" && htmlStr != "" {
						if parsedThumb, err := parser.ParseArticleOfHTML(htmlStr); err == nil {
							if parsedThumb.TopImage != "" {
								_ = postRepo.UpdateThumbnailURL(ctx, saved.ID, parsedThumb.TopImage)
							}
						}
					}
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
						// 썸네일 저장
						if parsed.TopImage != "" {
							_ = postRepo.UpdateThumbnailURL(ctx, saved.ID, parsed.TopImage)
						}
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
				// 썸네일 저장
				if parsed.TopImage != "" {
					_ = postRepo.UpdateThumbnailURL(ctx, saved.ID, parsed.TopImage)
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
				if err := postRepo.UpdateAIGeneratedInfo(ctx, saved.ID, info); err != nil {
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
	return nil
}
