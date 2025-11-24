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

// HandlePostCreated 포스트 생성 이벤트 처리 (HTML 렌더링만 수행, DB 접근 없음)
func (h *EventHandlers) HandlePostCreated(ctx context.Context, event *events.PostCreatedEvent) error {
	config.Logger.Infof("handling PostCreated event for post: %s", event.Title)

	// 1. HTML 렌더링
	htmlStr, err := renderer.RenderHTML(event.Link)
	if err != nil {
		config.Logger.Errorf("failed to render HTML for %s: %v", event.Link, err)
		return err
	}

	// 2. 썸네일 파싱
	thumbnailURL, err := parser.ParseTopImageFromHTML(htmlStr, event.Link)
	if err != nil {
		config.Logger.Warnf("failed to parse thumbnail for %s: %v", event.Link, err)
		// 썸네일 실패는 치명적이지 않음, 계속 진행
	}

	// 3. PostHTMLRendered 이벤트 발행 (Aggregate가 DB 저장)
	if err := h.eventService.PublishPostHTMLRendered(ctx, event.PostID, event.Link, htmlStr, thumbnailURL); err != nil {
		config.Logger.Errorf("failed to publish PostHTMLRendered event: %v", err)
		return err
	}

	config.Logger.Infof("post HTML rendered for: %s", event.Link)
	return nil
}

// HandlePostContentParsed 본문 파싱 완료 이벤트 처리 (이벤트에서 RenderedHTML 받아서 AI 요약, DB 접근 없음)
func (h *EventHandlers) HandlePostContentParsed(ctx context.Context, event *events.PostContentParsedEvent) error {
	allowed, err := h.summaryQuota.WaitAndReserve(ctx)
	if err != nil {
		config.Logger.Errorf("failed to apply summary quota for %s: %v", event.Link, err)
		return err
	}
	if !allowed {
		config.Logger.Warnf("summary daily quota exceeded, skip summarization for %s", event.Link)
		return nil
	}

	config.Logger.Infof("handling PostContentParsed event for post: %s", event.Link)

	// 이벤트에서 RenderedHTML 확인
	if event.RenderedHTML == "" {
		config.Logger.Errorf("post rendered HTML is empty in event for %s", event.Link)
		return fmt.Errorf("post rendered HTML is empty")
	}

	// HTML에서 plain text 추출
	plainText, err := parser.ParseHtmlWithReadability(event.RenderedHTML)
	if err != nil {
		config.Logger.Errorf("failed to parse HTML to plain text for %s: %v", event.Link, err)
		return err
	}

	// AI 요약
	summaryResult, reqLog, err := summarizer.SummarizeText(plainText)
	if err != nil || summaryResult.Error != nil {
		config.Logger.Errorf("failed to summarize %s: %v", event.Link, err)
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

	// PostSummarized 이벤트 발행 (Aggregate가 DB 저장)
	if err := h.eventService.PublishPostSummarized(ctx, event.PostID, event.Link, summary); err != nil {
		config.Logger.Errorf("failed to publish PostSummarized event: %v", err)
		return err
	}

	config.Logger.Infof("post AI summary completed for: %s", event.Link)
	return nil
}

// HandlePostThumbnailParseRequested 썸네일 파싱 요청 이벤트 처리 (RenderedHTML 기반)
func (h *EventHandlers) HandlePostThumbnailParseRequested(ctx context.Context, event *events.PostThumbnailParseRequestedEvent) error {
config.Logger.Infof("handling PostThumbnailParseRequested event for post: %s", event.Link)

if event.RenderedHTML == "" {
config.Logger.Errorf("empty rendered HTML for post: %s", event.Link)
return fmt.Errorf("empty rendered HTML")
}

// RenderedHTML에서 썸네일 파싱
thumbnailURL, err := parser.ParseTopImageFromHTML(event.RenderedHTML, event.Link)
if err != nil {
config.Logger.Warnf("failed to parse thumbnail for %s: %v", event.Link, err)
// 썸네일 실패는 치명적이지 않음
}

// PostThumbnailParsed 이벤트 발행
if err := h.eventService.PublishPostThumbnailParsed(ctx, event.PostID, event.Link, thumbnailURL); err != nil {
config.Logger.Errorf("failed to publish PostThumbnailParsed event: %v", err)
return err
}

config.Logger.Infof("post thumbnail parsed for: %s", event.Link)
return nil
}
