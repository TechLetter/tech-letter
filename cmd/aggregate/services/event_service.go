package services

import (
	"context"
	"fmt"
	"time"

	"tech-letter/eventbus"
	"tech-letter/events"
	"tech-letter/models"

	"github.com/google/uuid"
)

// EventService Aggregate용 이벤트 발행 서비스
type EventService struct {
	bus eventbus.EventBus
}

// NewEventService 새로운 이벤트 서비스 생성
func NewEventService(bus eventbus.EventBus) *EventService {
	return &EventService{
		bus: bus,
	}
}

// PublishPostSummaryRequested 는 새 포스트에 대한 요약 요청(PostSummaryRequested) 이벤트를 발행한다.
func (s *EventService) PublishPostSummaryRequested(ctx context.Context, post *models.Post) error {
	e := events.PostSummaryRequestedEvent{
		BaseEvent: events.BaseEvent{
			ID:        uuid.New().String(),
			Type:      events.PostSummaryRequested,
			Timestamp: time.Now(),
			Source:    "aggregate",
			Version:   "1.0",
		},
		PostID:   post.ID,
		BlogID:   post.BlogID,
		BlogName: post.BlogName,
		Title:    post.Title,
		Link:     post.Link,
	}

	evt, err := eventbus.NewJSONEvent("", e, 0)
	if err != nil {
		return fmt.Errorf("failed to build event: %w", err)
	}
	return s.bus.Publish(ctx, eventbus.TopicPostEvents.Base(), evt)
}

// PublishPostThumbnailRequested 썸네일 파싱 요청 이벤트 발행
func (s *EventService) PublishPostThumbnailRequested(ctx context.Context, post *models.Post) error {
	e := events.PostThumbnailRequestedEvent{
		BaseEvent: events.BaseEvent{
			ID:        uuid.New().String(),
			Type:      events.PostThumbnailRequested,
			Timestamp: time.Now(),
			Source:    "aggregate",
			Version:   "1.0",
		},
		PostID: post.ID,
		Link:   post.Link,
	}

	evt, err := eventbus.NewJSONEvent("", e, 0)
	if err != nil {
		return fmt.Errorf("failed to build event: %w", err)
	}
	return s.bus.Publish(ctx, eventbus.TopicPostEvents.Base(), evt)
}
