package main

import (
	"context"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/feeder"
	"tech-letter/models"
	"tech-letter/parser"
	"tech-letter/renderer"
	"tech-letter/repositories"
	"tech-letter/summarizer"
	"time"
)

func main() {
	config.InitApp()
	config.InitLogger()

	ctx := context.Background()
	if err := db.Init(ctx); err != nil {
		config.Logger.Errorf("failed to initialize MongoDB: %v", err)
	}

	if err := runOnce(ctx); err != nil {
		config.Logger.Errorf("aggregate runOnce error: %v", err)
	}

	ticker := time.NewTicker(time.Hour)
	defer ticker.Stop()

	for range ticker.C {
		if err := runOnce(ctx); err != nil {
			config.Logger.Errorf("aggregate runOnce error: %v", err)
		}
	}
}

func runOnce(ctx context.Context) error {
	blogRepo := repositories.NewBlogRepository(db.Database())
	postRepo := repositories.NewPostRepository(db.Database())

	cfgBlogs := config.GetConfig().Blogs
	if len(cfgBlogs) == 0 {
		config.Logger.Warn("no blogs configured in config.yaml (key: blogs)")
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
			config.Logger.Errorf("failed to upsert blog %s: %v", b.Name, err)
		}
	}

	for _, blog := range cfgBlogs {
		// Find blog doc to get BlogID
		blogDoc, err := blogRepo.GetByRSSURL(ctx, blog.RSSURL)
		if err != nil {
			config.Logger.Errorf("skip fetching posts for %s: failed to find blog doc: %v", blog.Name, err)
			continue
		}

		feed, err := feeder.FetchRssFeeds(blog.RSSURL, config.GetConfig().BlogFetchBatchSize)
		if err != nil {
			config.Logger.Errorf("fetch rss error for %s: %v", blog.Name, err)
			continue
		}

		for _, item := range feed {
			// Ensure post exists by link (no upsert)
			exists, err := postRepo.IsExistByLink(ctx, item.Link)
			if err != nil {
				config.Logger.Errorf("failed to check post existence (link=%s): %v", item.Link, err)
				continue
			}
			if !exists {
				p := &models.Post{
					BlogID:   blogDoc.ID,
					BlogName: blogDoc.Name,
					Title:    item.Title,
					Link:     item.Link,
				}
				if !item.PublishedAt.IsZero() {
					p.PublishedAt = item.PublishedAt
				}
				if _, err := postRepo.Insert(ctx, p); err != nil {
					config.Logger.Errorf("failed to insert post (blog=%s, title=%s): %v", blog.Name, item.Title, err)
					continue
				}
			}

			// Load saved post to get its ID
			savedPost, err := postRepo.FindByLink(ctx, item.Link)
			if err != nil {
				config.Logger.Errorf("failed to reload post (blog=%s, link=%s): %v", blog.Name, item.Link, err)
				continue
			}

			// Prepare flags from existing doc
			flags := savedPost.Status

			if flags.HTMLFetched && flags.TextParsed && flags.AISummarized {
				config.Logger.Debugf("skip processing post (blog=%s, link=%s): already processed", blog.Name, item.Link)
				continue
			}

			// 1) HTML 단계: 렌더링은 메모리 상에서만 수행 (저장하지 않음)
			htmlStr, err := renderer.RenderHTML(item.Link)
			if err != nil {
				config.Logger.Errorf("failed to render HTML: %v", err)
				continue
			}

			config.Logger.Infof("rendered HTML for %s: %s", item.Title, item.Link)

			flags.HTMLFetched = true
			if err := postRepo.UpdateStatusFlags(ctx, savedPost.ID, flags); err != nil {
				config.Logger.Errorf("failed to update post status flags: %v", err)
				continue
			}

			// 2) TEXT 단계: 파싱을 메모리 상에서만 수행 (저장하지 않음)
			article, err := parser.ParseArticleOfHTML(htmlStr)
			if err != nil {
				config.Logger.Errorf("failed to parse HTML: %v", err)
				continue
			}

			if article.TopImage != "" && savedPost.ThumbnailURL == "" {
				_ = postRepo.UpdateThumbnailURL(ctx, savedPost.ID, article.TopImage)
			}

			flags.TextParsed = true
			if err := postRepo.UpdateStatusFlags(ctx, savedPost.ID, flags); err != nil {
				config.Logger.Errorf("failed to update post status flags: %v", err)
				continue
			}

			config.Logger.Infof("parsed Plain Text for %s: %s", item.Title, item.Link)

			// 3) AI 단계: AI를 메모리 상에서만 수행 (저장하지 않음)
			if !flags.AISummarized {
				summaryResult, reqLog, err := summarizer.SummarizeText(article.PlainTextContent)
				if err != nil || summaryResult.Error != nil {
					config.Logger.Errorf("failed to summarize: %v", err)
					continue
				}
				config.Logger.Infof("model:%s time:%s input:%d output:%d total:%d",
					reqLog.ModelName,
					reqLog.GeneratedAt,
					reqLog.TokenUsage.InputTokens,
					reqLog.TokenUsage.OutputTokens,
					reqLog.TokenUsage.TotalTokens)

				// Denormalized snapshot on posts (single summary field)
				summary := models.AISummary{
					Categories:  summaryResult.Categories,
					Tags:        summaryResult.Tags,
					Summary:     summaryResult.Summary,
					ModelName:   reqLog.ModelName,
					GeneratedAt: reqLog.GeneratedAt,
				}
				if err := postRepo.UpdateAISummary(ctx, savedPost.ID, summary); err != nil {
					config.Logger.Errorf("failed to update post AISummary: %v", err)
					continue
				}

				flags.AISummarized = true
				if err := postRepo.UpdateStatusFlags(ctx, savedPost.ID, flags); err != nil {
					config.Logger.Errorf("failed to update post status flags: %v", err)
					continue
				}

				config.Logger.Infof("summarized %s: %s", item.Title, item.Link)
			}
		}
	}
	return nil
}
