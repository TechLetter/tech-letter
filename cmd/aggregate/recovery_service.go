package main

import (
	"context"

	"tech-letter/cmd/aggregate/services"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/repositories"
)

// SummaryRecoveryService 는 요약이 완료되지 않은 포스트들에 대해
// PostCreated 이벤트를 재발행하여 요약을 재시도하는 책임을 가진다.
type SummaryRecoveryService struct {
	eventService *services.EventService
	postRepo     *repositories.PostRepository
}

// NewSummaryRecoveryService 새로운 요약 복구 서비스를 생성한다.
func NewSummaryRecoveryService(eventService *services.EventService) *SummaryRecoveryService {
	return &SummaryRecoveryService{
		eventService: eventService,
		postRepo:     repositories.NewPostRepository(db.Database()),
	}
}

// RunRecovery 는 아직 AI 요약이 완료되지 않은 포스트 일부를 선택하여
// PostCreated 이벤트를 다시 발행한다.
func (s *SummaryRecoveryService) RunRecovery(ctx context.Context, limit int64) error {
	posts, err := s.postRepo.FindUnsummarized(ctx, limit)
	if err != nil {
		return err
	}

	for _, p := range posts {
		if err := s.eventService.PublishPostCreated(ctx, &p); err != nil {
			config.Logger.Errorf("failed to re-publish PostCreated for unsummarized post %s: %v", p.ID.Hex(), err)
		} else {
			config.Logger.Infof("re-published PostCreated for unsummarized post: %s", p.ID.Hex())
		}
	}

	return nil
}
