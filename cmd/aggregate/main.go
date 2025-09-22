package main

import (
	"context"
	"log"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/feeder"
	"tech-letter/models"
	"tech-letter/parser"
	"tech-letter/renderer"
	"tech-letter/repositories"
	"tech-letter/summarizer"
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

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
	postAISummaryRepo := repositories.NewPostAISummaryRepository(db.Database())

	cfgBlogs := config.GetConfig().Blogs
	if len(cfgBlogs) == 0 {
		log.Printf("no blogs configured in config.yaml (key: blogs)")
		return nil
	}

	for _, b := range cfgBlogs {
		mb := &models.Blog{
			Name:   b.Name,
			URL:    b.URL,
			RSSURL: b.RSSURL,
			BlogType: func() string {
				if b.BlogType != "" {
					return b.BlogType
				}
				return "company"
			}(),
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

			// Load savedPost post to get its ID
			savedPost, err := postRepo.FindByBlogAndLink(ctx, blogDoc.ID, item.Link)
			if err != nil {
				log.Printf("failed to reload post (blog=%s, link=%s): %v", blog.Name, item.Link, err)
				continue
			}

			// Prepare flags from existing doc
			flags := savedPost.Status

			if flags.HTMLFetched && flags.TextParsed && flags.AISummarized {
				log.Printf("skip processing post (blog=%s, link=%s): already processed", blog.Name, item.Link)
				continue
			}

			// 1) HTML 단계: StatusFlags 기반으로 수행
			var htmlStr string
			if !flags.HTMLFetched {
				start := time.Now()
				var err error
				htmlStr, err = renderer.RenderHTML(item.Link)
				dur := time.Since(start)
				if err != nil {
					log.Printf("failed to render HTML: %v", err)
					continue
				}
				if _, err := postHTMLRepo.UpsertByPost(ctx, &models.PostHTML{
					PostID:          savedPost.ID,
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
				_ = postRepo.UpdateStatusFlags(ctx, savedPost.ID, flags)
				log.Printf("fetched Raw HTML for %s: %s", item.Title, item.Link)
			} else {
				if savedHtmlStr, err := postHTMLRepo.FindByPostID(ctx, savedPost.ID); err == nil && savedHtmlStr.RawHTML != "" {
					htmlStr = savedHtmlStr.RawHTML
				} else {
					// 플래그는 true인데 데이터가 없으면 보수적으로 재수집
					start := time.Now()
					var err error
					htmlStr, err = renderer.RenderHTML(item.Link)
					dur := time.Since(start)
					if err != nil {
						log.Printf("failed to render HTML (fallback): %v", err)
						continue
					}
					if _, err := postHTMLRepo.UpsertByPost(ctx, &models.PostHTML{
						PostID:          savedPost.ID,
						RawHTML:         htmlStr,
						FetchedAt:       time.Now(),
						FetchDurationMs: dur.Milliseconds(),
						HTMLSizeBytes:   int64(len([]byte(htmlStr))),
						BlogName:        blogDoc.Name,
						PostTitle:       item.Title,
					}); err != nil {
						log.Printf("failed to upsert post_html (fallback): %v", err)
						continue
					}
					log.Printf("re-fetched Raw HTML for %s: %s", item.Title, item.Link)
				}
			}

			// 2) TEXT 단계: StatusFlags 기반으로 수행
			var savedPlainText string
			if !flags.TextParsed {
				parsed, err := parser.ParseArticleOfHTML(htmlStr)
				if err != nil {
					log.Printf("failed to parse HTML: %v", err)
					continue
				}
				savedPlainText = parsed.PlainTextContent
				if _, err := postTextRepo.UpsertByPost(ctx, &models.PostText{
					PostID:    savedPost.ID,
					PlainText: savedPlainText,
					ParsedAt:  time.Now(),
					WordCount: len([]rune(savedPlainText)),
					BlogName:  blogDoc.Name,
					PostTitle: item.Title,
				}); err != nil {
					log.Printf("failed to upsert post_text: %v", err)
					continue
				}
				if parsed.TopImage != "" {
					_ = postRepo.UpdateThumbnailURL(ctx, savedPost.ID, parsed.TopImage)
				}
				flags.TextParsed = true
				_ = postRepo.UpdateStatusFlags(ctx, savedPost.ID, flags)
				log.Printf("parsed Plain Text for %s: %s", item.Title, item.Link)
			} else {
				if txt, err := postTextRepo.FindByPostID(ctx, savedPost.ID); err == nil && txt.PlainText != "" {
					savedPlainText = txt.PlainText
					if savedPost.ThumbnailURL == "" && htmlStr != "" {
						if parsedThumb, err := parser.ParseArticleOfHTML(htmlStr); err == nil && parsedThumb.TopImage != "" {
							_ = postRepo.UpdateThumbnailURL(ctx, savedPost.ID, parsedThumb.TopImage)
						}
					}
				} else {
					// 플래그는 true인데 데이터가 없으면 보수적으로 재파싱
					parsed, err := parser.ParseArticleOfHTML(htmlStr)
					if err != nil {
						log.Printf("failed to parse HTML (fallback): %v", err)
						continue
					}
					savedPlainText = parsed.PlainTextContent
					if _, err := postTextRepo.UpsertByPost(ctx, &models.PostText{
						PostID:    savedPost.ID,
						PlainText: savedPlainText,
						ParsedAt:  time.Now(),
						WordCount: len([]rune(savedPlainText)),
						BlogName:  blogDoc.Name,
						PostTitle: item.Title,
					}); err != nil {
						log.Printf("failed to upsert post_text (fallback): %v", err)
						continue
					}
				}
			}

			// 3) AI SUMMARY 단계: 필요 시에만 실행, 성공 시 플래그 갱신
			if !flags.AISummarized {
				summaryResult, reqLog, err := summarizer.SummarizeText(savedPlainText)
				if err != nil || summaryResult.Error != nil {
					log.Printf("failed to summarize: %v", err)
					continue
				}

				// Denormalized snapshot on posts
				summary := models.AISummary{
					Categories:   summaryResult.Categories,
					Tags:         summaryResult.Tags,
					SummaryShort: summaryResult.SummaryShort,
					SummaryLong:  summaryResult.SummaryLong,
					ModelName:    reqLog.ModelName,
					GeneratedAt:  reqLog.GeneratedAt,
				}
				if err := postRepo.UpdateAISummary(ctx, savedPost.ID, summary); err != nil {
					log.Printf("failed to update post AISummary: %v", err)
					continue
				}

				// Insert AI log (system monitoring)
				aiLogRes, err := aiLogRepo.Insert(ctx, models.AILog{
					ModelName:      reqLog.ModelName,
					ModelVersion:   reqLog.ModelVersion,
					InputTokens:    reqLog.TokenUsage.InputTokens,
					OutputTokens:   reqLog.TokenUsage.OutputTokens,
					TotalTokens:    reqLog.TokenUsage.TotalTokens,
					DurationMs:     reqLog.LatencyMs,
					InputPrompt:    savedPlainText,
					OutputResponse: reqLog.Response,
					RequestedAt:    reqLog.GeneratedAt.Add(-time.Duration(reqLog.LatencyMs) * time.Millisecond),
					CompletedAt:    reqLog.GeneratedAt,
				})
				if err != nil {
					log.Printf("failed to insert AI log: %v", err)
					continue
				}

				// Link AI log to a normalized PostAISummary document
				var aiLogID primitive.ObjectID
				if aiLogRes != nil {
					if oid, ok := aiLogRes.InsertedID.(primitive.ObjectID); ok {
						aiLogID = oid
					}
				}
				// Insert PostAISummary (no version, multiple entries per post allowed)
				if _, err := postAISummaryRepo.Insert(ctx, models.PostAISummary{
					PostID:       savedPost.ID,
					AILogID:      aiLogID,
					Categories:   summary.Categories,
					Tags:         summary.Tags,
					SummaryShort: summary.SummaryShort,
					SummaryLong:  summary.SummaryLong,
					ModelName:    summary.ModelName,
					GeneratedAt:  summary.GeneratedAt,
				}); err != nil {
					log.Printf("failed to insert PostAISummary: %v", err)
					continue
				}
				if !flags.AISummarized {
					flags.AISummarized = true
					if err := postRepo.UpdateStatusFlags(ctx, savedPost.ID, flags); err != nil {
						log.Printf("failed to update post status flags: %v", err)
						continue
					}
				}
				log.Printf("summarized %s: %s", item.Title, item.Link)
			}
		}
	}
	return nil
}
