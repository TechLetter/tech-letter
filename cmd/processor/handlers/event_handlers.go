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

// HandlePostCreated 포스트 생성 이벤트 처리
func (h *EventHandlers) HandlePostCreated(ctx context.Context, event interface{}) error {
	postCreatedEvent, ok := event.(*events.PostCreatedEvent)
	if !ok {
		return fmt.Errorf("invalid event type for PostCreated handler")
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

	config.Logger.Infof("handling PostCreated event for post: %s", postCreatedEvent.Title)

	// HTML 렌더링
	htmlStr, err := renderer.RenderHTML(postCreatedEvent.Link)
	if err != nil {
		config.Logger.Errorf("failed to render HTML for %s: %v", postCreatedEvent.Link, err)
		return err
	}

	// 텍스트 파싱
	article, err := parser.ParseArticleOfHTML(htmlStr)
	if err != nil {
		config.Logger.Errorf("failed to parse HTML for %s: %v", postCreatedEvent.Link, err)
		return err
	}

	// AI 요약
	summaryResult, reqLog, err := summarizer.SummarizeText(article.PlainTextContent)
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

	if err := h.eventService.PublishPostSummarized(ctx, postCreatedEvent.PostID, postCreatedEvent.Link, article.TopImage, summary); err != nil {
		config.Logger.Errorf("failed to publish PostSummarized event: %v", err)
		return err
	}

	config.Logger.Infof("post processing pipeline completed for: %s", postCreatedEvent.Link)
	return nil
}

// 이전에 사용하던 중간 단계 이벤트(PostHTMLFetched, PostTextParsed)와
// DB 업데이트 로직은 Aggregate 쪽으로 옮겨졌고, Processor는 더 이상 해당 책임을 갖지 않는다.
