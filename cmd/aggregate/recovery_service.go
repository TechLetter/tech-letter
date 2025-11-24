package main

import (
	"context"

	"tech-letter/cmd/aggregate/services"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/repositories"
)

// RecoveryService 는 요약이 완료되지 않은 포스트들에 대해
// 요약 요청 이벤트(PostCreated)를 재발행하여 요약을 재시도하는 책임을 가진다.
type RecoveryService struct {
	eventService *services.EventService
	postRepo     *repositories.PostRepository
}

// NewRecoveryService 새로운 요약 복구 서비스를 생성한다.
func NewRecoveryService(eventService *services.EventService) *RecoveryService {
	return &RecoveryService{
		eventService: eventService,
		postRepo:     repositories.NewPostRepository(db.Database()),
	}
}

// RunSummaryRecovery 는 아직 AI 요약이 완료되지 않은 포스트 일부를 선택하여
// 요약 요청 이벤트(PostCreated)를 다시 발행한다.
func (s *RecoveryService) RunSummaryRecovery(ctx context.Context, limit int64) error {
	posts, err := s.postRepo.FindUnsummarized(ctx, limit)
	if err != nil {
		return err
	}

	for _, p := range posts {
		if err := s.eventService.PublishPostSummaryRequested(ctx, &p); err != nil {
			config.Logger.Errorf("failed to re-publish PostSummaryRequested for unsummarized post %s: %v", p.ID.Hex(), err)
		} else {
			config.Logger.Infof("re-published PostSummaryRequested for unsummarized post: %s", p.ID.Hex())
		}
	}

	return nil
}

func (s *RecoveryService) RunThumbnailRecovery(ctx context.Context, limit int64) error {
	posts, err := s.postRepo.FindThumbnailNotParsed(ctx, limit)
	if err != nil {
		return err
	}

	for _, p := range posts {
		if err := s.eventService.PublishPostThumbnailRequested(ctx, &p); err != nil {
			config.Logger.Errorf("failed to publish PostThumbnailRequested for post %s: %v", p.ID.Hex(), err)
		} else {
			config.Logger.Infof("published PostThumbnailRequested for post: %s", p.ID.Hex())
		}
	}

	return nil
}
