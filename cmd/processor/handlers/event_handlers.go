package handlers

import (
	"context"
	"fmt"

	"tech-letter/cmd/processor/parser"
	"tech-letter/cmd/processor/quota"
	"tech-letter/cmd/processor/renderer"
	eventServices "tech-letter/cmd/processor/services"
	"tech-letter/cmd/processor/summarizer"
	"tech-letter/config"
	"tech-letter/events"
	"tech-letter/models"
)

// EventHandlers 이벤트 핸들러 모음
type EventHandlers struct {
	eventService *eventServices.EventService
	summaryQuota *quota.SummaryQuotaLimiter
}

// NewEventHandlers 새로운 이벤트 핸들러 생성

func NewEventHandlers(eventService *eventServices.EventService, summaryQuota *quota.SummaryQuotaLimiter) *EventHandlers {
	return &EventHandlers{
		eventService: eventService,
		summaryQuota: summaryQuota,
	}
}

// HandlePostSummaryRequested 포스트 요약 요청 이벤트 처리
func (h *EventHandlers) HandlePostSummaryRequested(ctx context.Context, event interface{}) error {
	postCreatedEvent, ok := event.(*events.PostSummaryRequestedEvent)
	if !ok {
		return fmt.Errorf("invalid event type for PostSummaryRequested handler")
	}

	allowed, err := h.summaryQuota.WaitAndReserve(ctx)
	if err != nil {
		config.Logger.Errorf("failed to apply summary quota for %s: %v", postCreatedEvent.Link, err)
		return err
	}
	if !allowed {
		// 일일 한도 초과: 이번 이벤트는 요약을 스킵한다.
		// 에러를 반환하지 않음으로써 DLQ로 가지 않고 정상 소비되도록 한다.
		config.Logger.Warnf("summary daily quota exceeded, skip summarization for %s", postCreatedEvent.Link)
		return nil
	}

	config.Logger.Infof("handling PostSummaryRequested event for post: %s", postCreatedEvent.Title)

	// HTML 렌더링
	htmlStr, err := renderer.RenderHTML(postCreatedEvent.Link)
	if err != nil {
		config.Logger.Errorf("failed to render HTML for %s: %v", postCreatedEvent.Link, err)
		return err
	}

	// 텍스트 파싱
	plainText, err := parser.ParseHtmlWithReadability(htmlStr)
	if err != nil {
		config.Logger.Errorf("failed to parse HTML for %s: %v", postCreatedEvent.Link, err)
		return err
	}

	// AI 요약
	summaryResult, reqLog, err := summarizer.SummarizeText(plainText)
	if err != nil || summaryResult.Error != nil {
		config.Logger.Errorf("failed to summarize %s: %v", postCreatedEvent.Link, err)
		return err
	}

	config.Logger.Infof("AI summary completed - model:%s time:%s input:%d output:%d total:%d",
		reqLog.ModelName,
		reqLog.GeneratedAt,
		reqLog.TokenUsage.InputTokens,
		reqLog.TokenUsage.OutputTokens,
		reqLog.TokenUsage.TotalTokens,
	)

	summary := models.AISummary{
		Categories:  summaryResult.Categories,
		Tags:        summaryResult.Tags,
		Summary:     summaryResult.Summary,
		ModelName:   reqLog.ModelName,
		GeneratedAt: reqLog.GeneratedAt,
	}

	if err := h.eventService.PublishPostSummarized(ctx, postCreatedEvent.PostID, postCreatedEvent.Link, summary); err != nil {
		config.Logger.Errorf("failed to publish PostSummarized event: %v", err)
		return err
	}

	config.Logger.Infof("post processing pipeline completed for: %s", postCreatedEvent.Link)
	return nil
}

// HandlePostThumbnailRequested 썸네일 파싱 요청 이벤트 처리
func (h *EventHandlers) HandlePostThumbnailRequested(ctx context.Context, event *events.PostThumbnailRequestedEvent) error {
	config.Logger.Infof("handling PostThumbnailRequested event for post: %s", event.Link)

	// HTML 렌더링
	htmlStr, err := renderer.RenderHTML(event.Link)
	if err != nil {
		config.Logger.Errorf("failed to render HTML for thumbnail parsing %s: %v", event.Link, err)
		return err
	}

	// 썸네일 파싱
	thumbnailURL, err := parser.ParseTopImageFromHTML(htmlStr, event.Link)
	if err != nil {
		config.Logger.Errorf("failed to parse thumbnail for %s: %v", event.Link, err)
		return err
	}

	if err := h.eventService.PublishPostThumbnailParsed(ctx, event.PostID, event.Link, thumbnailURL); err != nil {
		config.Logger.Errorf("failed to publish PostThumbnailParsed event: %v", err)
		return err
	}

	config.Logger.Infof("thumbnail parsing completed for: %s (thumbnail=%s)", event.Link, thumbnailURL)
	return nil
}
