package handlers

import (
	"context"
	"time"

	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/events"
	"tech-letter/models"
	"tech-letter/repositories"
)

// EventHandlers 집계(Aggregate) 서버용 이벤트 핸들러 모음
// Processor는 요약까지의 계산만 담당하고, DB 업데이트는 Aggregate가 담당한다.
type EventHandlers struct {
	postRepo *repositories.PostRepository
}

// NewEventHandlers 새로운 이벤트 핸들러 생성
func NewEventHandlers() *EventHandlers {
	return &EventHandlers{
		postRepo: repositories.NewPostRepository(db.Database()),
	}
}

// HandlePostSummarized Processor에서 발행한 PostSummarized 이벤트를 받아 DB에 결과를 반영한다.
func (h *EventHandlers) HandlePostSummarized(ctx context.Context, event *events.PostSummarizedEvent) error {
	config.Logger.Infof("aggregate handling PostSummarized event for post: %s", event.Link)

	summary := models.AISummary{
		Categories:  event.Categories,
		Tags:        event.Tags,
		Summary:     event.Summary,
		ModelName:   event.ModelName,
		GeneratedAt: time.Now(),
	}

	if err := h.postRepo.UpdateAISummary(ctx, event.PostID, summary); err != nil {
		config.Logger.Errorf("failed to update AI summary for %s: %v", event.PostID.Hex(), err)
		return err
	}

	if err := h.postRepo.SetAISummarized(ctx, event.PostID, true); err != nil {
		config.Logger.Errorf("failed to update status flags for %s: %v", event.PostID.Hex(), err)
		return err
	}

	if event.ThumbnailURL != "" {
		if err := h.postRepo.UpdateThumbnailURL(ctx, event.PostID, event.ThumbnailURL); err != nil {
			config.Logger.Errorf("failed to update thumbnail URL for %s: %v", event.PostID.Hex(), err)
			return err
		}
	}

	config.Logger.Infof("aggregate DB updated for summarized post: %s", event.Link)
	return nil
}
