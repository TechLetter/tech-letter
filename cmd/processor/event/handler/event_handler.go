package handler

import (
	"context"
	"tech-letter/cmd/processor/event/dispatcher"
	"tech-letter/cmd/processor/parser"
	"tech-letter/cmd/processor/quota"
	"tech-letter/cmd/processor/renderer"
	"tech-letter/cmd/processor/summarizer"
	"tech-letter/config"
	"tech-letter/events"
	"tech-letter/models"
)

type EventHandlers struct {
	eventDispatcher *dispatcher.EventDispatcher
	summaryQuota    *quota.SummaryQuotaLimiter
}

func NewEventHandlers(eventDispatcher *dispatcher.EventDispatcher, summaryQuota *quota.SummaryQuotaLimiter) *EventHandlers {
	return &EventHandlers{
		eventDispatcher: eventDispatcher,
		summaryQuota:    summaryQuota,
	}
}

func (h *EventHandlers) HandlePostCreated(ctx context.Context, event *events.PostCreatedEvent) error {
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

	renderedHtml, err := renderer.RenderHTML(event.Link)
	if err != nil {
		config.Logger.Errorf("failed to render HTML for %s: %v", event.Link, err)
		return err
	}

	// HTML에서 plain text 추출
	plainText, err := parser.ParseHtmlWithReadability(renderedHtml)
	if err != nil {
		config.Logger.Errorf("failed to parse HTML to plain text for %s: %v", event.Link, err)
		return err
	}

	// 썸네일 URL 추출
	thumbnailUrl, err := parser.ParseTopImageFromHTML(renderedHtml, event.Link)
	if err != nil {
		config.Logger.Errorf("failed to parse thumbnail for %s: %v", event.Link, err)
		return err
	}
	if thumbnailUrl == "" {
		config.Logger.Warnf("no thumbnail found for %s", event.Link)
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
	if err := h.eventDispatcher.PublishPostSummarized(ctx, event.PostID, event.Link, renderedHtml, thumbnailUrl, summary); err != nil {
		config.Logger.Errorf("failed to publish PostSummarized event: %v", err)
		return err
	}

	config.Logger.Infof("post AI summary completed for: %s", event.Link)
	return nil
}
