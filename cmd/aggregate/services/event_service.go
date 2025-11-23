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

// PublishPostCreated 포스트 생성 이벤트 발행
func (s *EventService) PublishPostCreated(ctx context.Context, post *models.Post) error {
	e := events.PostCreatedEvent{
		BaseEvent: events.BaseEvent{
			ID:        uuid.New().String(),
			Type:      events.PostCreated,
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
