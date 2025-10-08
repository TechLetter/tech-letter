package handlers

import (
	"context"
	"fmt"

	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/events"
	"tech-letter/models"
	"tech-letter/cmd/processor/parser"
	"tech-letter/cmd/processor/renderer"
	"tech-letter/repositories"
	"tech-letter/cmd/processor/summarizer"
	eventServices "tech-letter/cmd/processor/services"
)

// EventHandlers 이벤트 핸들러 모음
type EventHandlers struct {
	eventService *eventServices.EventService
	postRepo     *repositories.PostRepository
}

// NewEventHandlers 새로운 이벤트 핸들러 생성
func NewEventHandlers(eventService *eventServices.EventService) *EventHandlers {
	return &EventHandlers{
		eventService: eventService,
		postRepo:     repositories.NewPostRepository(db.Database()),
	}
}

// HandlePostCreated 포스트 생성 이벤트 처리
func (h *EventHandlers) HandlePostCreated(ctx context.Context, event interface{}) error {
	postCreatedEvent, ok := event.(*events.PostCreatedEvent)
	if !ok {
		return fmt.Errorf("invalid event type for PostCreated handler")
	}

	config.Logger.Infof("handling PostCreated event for post: %s", postCreatedEvent.Title)

	// 포스트 조회
	post, err := h.postRepo.FindByID(ctx, postCreatedEvent.PostID)
	if err != nil {
		config.Logger.Errorf("failed to find post %s: %v", postCreatedEvent.PostID.Hex(), err)
		return err
	}

	// HTML 렌더링 단계 시작
	if !post.Status.HTMLFetched {
		if err := h.processHTMLStep(ctx, *post); err != nil {
			config.Logger.Errorf("failed to process HTML step for %s: %v", post.Link, err)
			return err
		}
	}

	return nil
}

// HandlePostHTMLFetched HTML 렌더링 완료 이벤트 처리
func (h *EventHandlers) HandlePostHTMLFetched(ctx context.Context, event interface{}) error {
	htmlFetchedEvent, ok := event.(*events.PostHTMLFetchedEvent)
	if !ok {
		return fmt.Errorf("invalid event type for PostHTMLFetched handler")
	}

	config.Logger.Infof("handling PostHTMLFetched event for post: %s", htmlFetchedEvent.Link)

	// 포스트 조회
	post, err := h.postRepo.FindByID(ctx, htmlFetchedEvent.PostID)
	if err != nil {
		config.Logger.Errorf("failed to find post %s: %v", htmlFetchedEvent.PostID.Hex(), err)
		return err
	}

	// 텍스트 파싱 단계 시작
	if post.Status.HTMLFetched && !post.Status.TextParsed {
		if err := h.processTextStep(ctx, *post); err != nil {
			config.Logger.Errorf("failed to process text step for %s: %v", post.Link, err)
			return err
		}
	}

	return nil
}

// HandlePostTextParsed 텍스트 파싱 완료 이벤트 처리
func (h *EventHandlers) HandlePostTextParsed(ctx context.Context, event interface{}) error {
	textParsedEvent, ok := event.(*events.PostTextParsedEvent)
	if !ok {
		return fmt.Errorf("invalid event type for PostTextParsed handler")
	}

	config.Logger.Infof("handling PostTextParsed event for post: %s", textParsedEvent.Link)

	// 포스트 조회
	post, err := h.postRepo.FindByID(ctx, textParsedEvent.PostID)
	if err != nil {
		config.Logger.Errorf("failed to find post %s: %v", textParsedEvent.PostID.Hex(), err)
		return err
	}

	// AI 요약 단계 시작
	if post.Status.HTMLFetched && post.Status.TextParsed && !post.Status.AISummarized {
		if err := h.processAIStep(ctx, *post); err != nil {
			config.Logger.Errorf("failed to process AI step for %s: %v", post.Link, err)
			return err
		}
	}

	return nil
}

// HandlePostSummarized AI 요약 완료 이벤트 처리
func (h *EventHandlers) HandlePostSummarized(ctx context.Context, event interface{}) error {
	summarizedEvent, ok := event.(*events.PostSummarizedEvent)
	if !ok {
		return fmt.Errorf("invalid event type for PostSummarized handler")
	}

	config.Logger.Infof("handling PostSummarized event for post: %s", summarizedEvent.Link)
	config.Logger.Infof("post processing completed for: %s", summarizedEvent.Link)

	return nil
}

// processHTMLStep HTML 렌더링 단계 처리
func (h *EventHandlers) processHTMLStep(ctx context.Context, post models.Post) error {
	_, err := renderer.RenderHTML(post.Link)
	if err != nil {
		config.Logger.Errorf("failed to render HTML for %s: %v", post.Link, err)
		return err
	}

	flags := post.Status
	flags.HTMLFetched = true
	if err := h.postRepo.UpdateStatusFlags(ctx, post.ID, flags); err != nil {
		config.Logger.Errorf("failed to update HTML status: %v", err)
		return err
	}

	// HTML 렌더링 완료 이벤트 발행
	if err := h.eventService.PublishPostHTMLFetched(ctx, post.ID, post.Link); err != nil {
		config.Logger.Errorf("failed to publish PostHTMLFetched event: %v", err)
	}

	config.Logger.Infof("HTML rendered for: %s", post.Title)
	return nil
}

// processTextStep 텍스트 파싱 단계 처리
func (h *EventHandlers) processTextStep(ctx context.Context, post models.Post) error {
	// HTML을 다시 렌더링해야 함 (메모리에 저장하지 않으므로)
	htmlStr, err := renderer.RenderHTML(post.Link)
	if err != nil {
		config.Logger.Errorf("failed to re-render HTML for text parsing %s: %v", post.Link, err)
		return err
	}

	article, err := parser.ParseArticleOfHTML(htmlStr)
	if err != nil {
		config.Logger.Errorf("failed to parse HTML for %s: %v", post.Link, err)
		return err
	}

	// 썸네일 업데이트
	if article.TopImage != "" && post.ThumbnailURL == "" {
		_ = h.postRepo.UpdateThumbnailURL(ctx, post.ID, article.TopImage)
	}

	flags := post.Status
	flags.TextParsed = true
	if err := h.postRepo.UpdateStatusFlags(ctx, post.ID, flags); err != nil {
		config.Logger.Errorf("failed to update text parsing status: %v", err)
		return err
	}

	// 텍스트 파싱 완료 이벤트 발행
	if err := h.eventService.PublishPostTextParsed(ctx, post.ID, post.Link, article.TopImage); err != nil {
		config.Logger.Errorf("failed to publish PostTextParsed event: %v", err)
	}

	config.Logger.Infof("text parsed for: %s", post.Title)
	return nil
}

// processAIStep AI 요약 단계 처리
func (h *EventHandlers) processAIStep(ctx context.Context, post models.Post) error {
	// HTML을 다시 렌더링하고 파싱해야 함
	htmlStr, err := renderer.RenderHTML(post.Link)
	if err != nil {
		config.Logger.Errorf("failed to re-render HTML for AI processing %s: %v", post.Link, err)
		return err
	}

	article, err := parser.ParseArticleOfHTML(htmlStr)
	if err != nil {
		config.Logger.Errorf("failed to re-parse HTML for AI processing %s: %v", post.Link, err)
		return err
	}

	summaryResult, reqLog, err := summarizer.SummarizeText(article.PlainTextContent)
	if err != nil || summaryResult.Error != nil {
		config.Logger.Errorf("failed to summarize %s: %v", post.Link, err)
		return err
	}

	config.Logger.Infof("AI summary completed - model:%s time:%s input:%d output:%d total:%d",
		reqLog.ModelName,
		reqLog.GeneratedAt,
		reqLog.TokenUsage.InputTokens,
		reqLog.TokenUsage.OutputTokens,
		reqLog.TokenUsage.TotalTokens)

	// AI 요약 저장
	summary := models.AISummary{
		Categories:  summaryResult.Categories,
		Tags:        summaryResult.Tags,
		Summary:     summaryResult.Summary,
		ModelName:   reqLog.ModelName,
		GeneratedAt: reqLog.GeneratedAt,
	}

	if err := h.postRepo.UpdateAISummary(ctx, post.ID, summary); err != nil {
		config.Logger.Errorf("failed to update AI summary: %v", err)
		return err
	}

	flags := post.Status
	flags.AISummarized = true
	if err := h.postRepo.UpdateStatusFlags(ctx, post.ID, flags); err != nil {
		config.Logger.Errorf("failed to update AI summary status: %v", err)
		return err
	}

	// AI 요약 완료 이벤트 발행
	if err := h.eventService.PublishPostSummarized(ctx, post.ID, post.Link, summary); err != nil {
		config.Logger.Errorf("failed to publish PostSummarized event: %v", err)
	}

	config.Logger.Infof("AI summarized: %s", post.Title)
	return nil
}
