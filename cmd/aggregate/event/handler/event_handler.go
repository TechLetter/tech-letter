package handler

import (
	"context"
	"time"

	"tech-letter/cmd/aggregate/event/dispatcher"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/events"
	"tech-letter/models"
	"tech-letter/repositories"
)

// EventHandler 집계(Aggregate) 서버용 이벤트 핸들러 모음
// Processor는 요약까지의 계산만 담당하고, DB 업데이트는 Aggregate가 담당한다.
type EventHandler struct {
	postRepo         *repositories.PostRepository
	eventDispatchers *dispatcher.EventDispatcher
}

// NewEventHandler 새로운 이벤트 핸들러 생성
func NewEventHandler(eventDispatcher *dispatcher.EventDispatcher) *EventHandler {
	return &EventHandler{
		postRepo:         repositories.NewPostRepository(db.Database()),
		eventDispatchers: eventDispatcher,
	}
}

// HandlePostSummarized Processor에서 발행한 PostSummarized 이벤트를 받아 DB에 결과를 반영한다.
func (h *EventHandler) HandlePostSummarized(ctx context.Context, event *events.PostSummarizedEvent) error {
	config.Logger.Infof("aggregate handling PostSummarized event for post: %s", event.Link)

	summary := models.AISummary{
		Categories:  event.Categories,
		Tags:        event.Tags,
		Summary:     event.Summary,
		ModelName:   event.ModelName,
		GeneratedAt: time.Now(),
	}

	updates := map[string]interface{}{
		"aisummary":            summary,
		"status.ai_summarized": true,
		"thumbnail_url":        event.ThumbnailURL,
		"rendered_html":        event.RenderedHTML,
	}

	if err := h.postRepo.UpdateFields(ctx, event.PostID, updates); err != nil {
		config.Logger.Errorf("failed to update post fields for %s: %v", event.PostID.Hex(), err)
		return err
	}

	config.Logger.Infof("aggregate DB updated for summarized post: %s", event.Link)
	return nil
}
