package main

import (
	"context"

	"go.mongodb.org/mongo-driver/bson/primitive"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/cmd/aggregate/feeder"
	"tech-letter/models"
	"tech-letter/repositories"
	eventServices "tech-letter/cmd/aggregate/services"
)

// AggregateService RSS 피드 수집 서비스
type AggregateService struct {
	eventService *eventServices.EventService
	blogRepo     *repositories.BlogRepository
	postRepo     *repositories.PostRepository
}

// NewAggregateService 새로운 집계 서비스 생성
func NewAggregateService(eventService *eventServices.EventService) *AggregateService {
	return &AggregateService{
		eventService: eventService,
		blogRepo:     repositories.NewBlogRepository(db.Database()),
		postRepo:     repositories.NewPostRepository(db.Database()),
	}
}

// RunFeedCollection RSS 피드 수집 및 새 포스트 생성
func (s *AggregateService) RunFeedCollection(ctx context.Context) error {
	cfgBlogs := config.GetConfig().Blogs
	if len(cfgBlogs) == 0 {
		config.Logger.Warn("no blogs configured in config.yaml (key: blogs)")
		return nil
	}

	// 블로그 정보 업데이트
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
		if _, err := s.blogRepo.UpsertByRSSURL(ctx, mb); err != nil {
			config.Logger.Errorf("failed to upsert blog %s: %v", b.Name, err)
		}
	}

	// 새 포스트 수집 및 이벤트 발행
	for _, blog := range cfgBlogs {
		if err := s.collectPostsFromBlog(ctx, blog); err != nil {
			config.Logger.Errorf("failed to collect posts from blog %s: %v", blog.Name, err)
		}
	}

	return nil
}

// collectPostsFromBlog 특정 블로그에서 포스트 수집
func (s *AggregateService) collectPostsFromBlog(ctx context.Context, blog config.BlogSource) error {
	// 블로그 문서 조회
	blogDoc, err := s.blogRepo.GetByRSSURL(ctx, blog.RSSURL)
	if err != nil {
		return err
	}

	// RSS 피드 가져오기
	feed, err := feeder.FetchRssFeeds(blog.RSSURL, config.GetConfig().BlogFetchBatchSize)
	if err != nil {
		return err
	}

	for _, item := range feed {
		// 포스트 존재 여부 확인
		exists, err := s.postRepo.IsExistByLink(ctx, item.Link)
		if err != nil {
			config.Logger.Errorf("failed to check post existence (link=%s): %v", item.Link, err)
			continue
		}

		if !exists {
			// 새 포스트 생성
			p := &models.Post{
				BlogID:   blogDoc.ID,
				BlogName: blogDoc.Name,
				Title:    item.Title,
				Link:     item.Link,
			}
			if !item.PublishedAt.IsZero() {
				p.PublishedAt = item.PublishedAt
			}

			result, err := s.postRepo.Insert(ctx, p)
			if err != nil {
				config.Logger.Errorf("failed to insert post (blog=%s, title=%s): %v", blog.Name, item.Title, err)
				continue
			}

			// Insert 후 생성된 ID를 포스트 객체에 설정
			if insertedID, ok := result.InsertedID.(primitive.ObjectID); ok {
				p.ID = insertedID
			} else {
				config.Logger.Errorf("failed to get inserted ID for post: %s", item.Title)
				continue
			}

			// 포스트 생성 이벤트 발행
			if err := s.eventService.PublishPostCreated(ctx, p); err != nil {
				config.Logger.Errorf("failed to publish PostCreated event: %v", err)
			} else {
				config.Logger.Infof("published PostCreated event for: %s (ID: %s)", item.Title, p.ID.Hex())
			}
		}
	}

	return nil
}
