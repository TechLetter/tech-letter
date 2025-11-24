package handlers

import (
	"context"
	"fmt"
	"time"

	eventServices "tech-letter/cmd/aggregate/services"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/events"
	"tech-letter/models"
	"tech-letter/repositories"
)

// EventHandlers 집계(Aggregate) 서버용 이벤트 핸들러 모음
// Processor는 요약까지의 계산만 담당하고, DB 업데이트는 Aggregate가 담당한다.
type EventHandlers struct {
	postRepo     *repositories.PostRepository
	eventService *eventServices.EventService
}

// NewEventHandlers 새로운 이벤트 핸들러 생성
func NewEventHandlers(eventService *eventServices.EventService) *EventHandlers {
	return &EventHandlers{
		postRepo:     repositories.NewPostRepository(db.Database()),
		eventService: eventService,
	}
}

// HandlePostHTMLRendered Processor에서 발행한 PostHTMLRendered 이벤트를 받아 DB에 HTML과 썸네일을 저장
// 다음 단계 이벤트를 자동으로 발행한다
func (h *EventHandlers) HandlePostHTMLRendered(ctx context.Context, event *events.PostHTMLRenderedEvent) error {
	config.Logger.Infof("aggregate handling PostHTMLRendered event for post: %s", event.Link)

	if event.RenderedHTML == "" {
		return fmt.Errorf("empty rendered HTML")
	}

	// DB 업데이트: RenderedHTML, ThumbnailURL
	updateFields := map[string]interface{}{
		"rendered_html": event.RenderedHTML,
		"thumbnail_url": event.ThumbnailURL,
	}

	if err := h.postRepo.UpdateFields(ctx, event.PostID, updateFields); err != nil {
		config.Logger.Errorf("failed to update rendered HTML for %s: %v", event.PostID.Hex(), err)
		return err
	}

	config.Logger.Infof("aggregate DB updated with rendered HTML for post: %s", event.Link)

	// 이미 요약된 포스트인지 확인
	post, err := h.postRepo.FindByID(ctx, event.PostID)
	if err != nil {
		config.Logger.Errorf("failed to get post %s: %v", event.PostID.Hex(), err)
		return err
	}

	// 이미 AI 요약이 완료된 경우 PostContentParsed 발행하지 않음
	if post.Status.AISummarized {
		config.Logger.Infof("post already summarized, skipping PostContentParsed for: %s", event.Link)
		return nil
	}

	if err := h.eventService.PublishPostContentParsed(ctx, event.PostID, event.Link, event.RenderedHTML); err != nil {
		config.Logger.Errorf("failed to publish PostContentParsed: %v", err)
		return err
	}
	config.Logger.Infof("published PostContentParsed for: %s", event.Link)
	return nil
}

// HandlePostThumbnailParsed 썸네일 파싱 완료 이벤트 처리
func (h *EventHandlers) HandlePostThumbnailParsed(ctx context.Context, event *events.PostThumbnailParsedEvent) error {
	config.Logger.Infof("aggregate handling PostThumbnailParsed event for post: %s", event.Link)

	if event.ThumbnailURL == "" {
		return fmt.Errorf("empty thumbnail URL")
	}
	// DB 업데이트: ThumbnailURL만 업데이트
	updateFields := map[string]interface{}{
		"thumbnail_url": event.ThumbnailURL,
	}

	if err := h.postRepo.UpdateFields(ctx, event.PostID, updateFields); err != nil {
		config.Logger.Errorf("failed to update thumbnail URL for %s: %v", event.PostID.Hex(), err)
		return err
	}

	config.Logger.Infof("aggregate DB updated thumbnail for post: %s", event.Link)

	// RenderedHTML 조회 (AI 요약을 위해)
	post, err := h.postRepo.FindByID(ctx, event.PostID)
	if err != nil {
		config.Logger.Errorf("failed to get post %s: %v", event.PostID.Hex(), err)
		return err
	}

	if post.RenderedHTML == "" {
		config.Logger.Errorf("post rendered HTML is empty for %s", event.Link)
		return fmt.Errorf("post rendered HTML is empty")
	}

	// 이미 AI 요약이 완료된 경우 PostContentParsed 발행하지 않음
	if post.Status.AISummarized {
		config.Logger.Infof("post already summarized, skipping PostContentParsed for: %s", event.Link)
		return nil
	}

	// PostContentParsed 발행 (AI 요약 단계로)
	if err := h.eventService.PublishPostContentParsed(ctx, event.PostID, event.Link, post.RenderedHTML); err != nil {
		config.Logger.Errorf("failed to publish PostContentParsed: %v", err)
		return err
	}

	config.Logger.Infof("published PostContentParsed after thumbnail parsing for: %s", event.Link)
	return nil
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

	config.Logger.Infof("aggregate DB updated for summarized post: %s", event.Link)
	return nil
}
