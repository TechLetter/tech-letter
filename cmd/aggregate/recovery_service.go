package main

import (
	"context"
	"time"

	"tech-letter/cmd/aggregate/services"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/repositories"
)

// RecoveryService 는 미완료 포스트들에 대해 적절한 이벤트를 재발행하는 책임을 가진다.
type RecoveryService struct {
	eventService *services.EventService
	postRepo     *repositories.PostRepository
}

// NewRecoveryService 새로운 복구 서비스를 생성한다.
func NewRecoveryService(eventService *services.EventService) *RecoveryService {
	return &RecoveryService{
		eventService: eventService,
		postRepo:     repositories.NewPostRepository(db.Database()),
	}
}

// RunHtmlRenderRecovery RenderedHTML이 없는 포스트를 조회하여 PostCreated 재발행
func (s *RecoveryService) RunHtmlRenderRecovery(ctx context.Context, limit int64, duration time.Duration) error {
	posts, err := s.postRepo.FindPostsWithoutRenderedHTML(ctx, limit, duration)
	if err != nil {
		return err
	}

	if len(posts) == 0 {
		config.Logger.Infof("RunHtmlRenderRecovery: no posts found for recovery - skipping")
		return nil
	}

	for _, p := range posts {
		if err := s.eventService.PublishPostCreated(ctx, &p); err != nil {
			config.Logger.Errorf("failed to re-publish PostCreated for post %s: %v", p.ID.Hex(), err)
		} else {
			config.Logger.Infof("re-published PostCreated for HTML render recovery: %s", p.ID.Hex())
		}
	}

	return nil
}

// RunThumbnailRecovery ThumbnailURL이 없지만 RenderedHTML은 있는 포스트를 조회하여 PostThumbnailParseRequested 재발행
func (s *RecoveryService) RunThumbnailRecovery(ctx context.Context, limit int64, duration time.Duration) error {
	posts, err := s.postRepo.FindPostsWithoutThumbnail(ctx, limit, duration)
	if err != nil {
		return err
	}

	if len(posts) == 0 {
		config.Logger.Infof("RunThumbnailRecovery: no posts found for recovery - skipping")
		return nil
	}

	for _, p := range posts {
		if p.RenderedHTML == "" {
			config.Logger.Warnf("post %s has no RenderedHTML, skipping", p.ID.Hex())
			continue
		}

		if err := s.eventService.PublishPostThumbnailParseRequested(ctx, p.ID, p.Link, p.RenderedHTML); err != nil {
			config.Logger.Errorf("failed to re-publish PostThumbnailParseRequested for post %s: %v", p.ID.Hex(), err)
		} else {
			config.Logger.Infof("re-published PostThumbnailParseRequested for thumbnail recovery: %s", p.ID.Hex())
		}
	}

	return nil
}

// RunSummaryRecovery 는 아직 AI 요약이 완료되지 않았지만 RenderedHTML은 있는 포스트를 조회하여 PostContentParsed 재발행
func (s *RecoveryService) RunSummaryRecovery(ctx context.Context, limit int64, duration time.Duration) error {
	posts, err := s.postRepo.FindPostsWithoutSummary(ctx, limit, duration)
	if err != nil {
		return err
	}

	if len(posts) == 0 {
		config.Logger.Infof("RunSummaryRecovery: no posts found for recovery - skipping")
		return nil
	}

	for _, p := range posts {
		if p.RenderedHTML == "" {
			config.Logger.Warnf("post %s has no RenderedHTML, skipping", p.ID.Hex())
			continue
		}

		if err := s.eventService.PublishPostContentParsed(ctx, p.ID, p.Link, p.RenderedHTML); err != nil {
			config.Logger.Errorf("failed to re-publish PostContentParsed for unsummarized post %s: %v", p.ID.Hex(), err)
		} else {
			config.Logger.Infof("re-published PostContentParsed for unsummarized post: %s", p.ID.Hex())
		}
	}

	return nil
}
