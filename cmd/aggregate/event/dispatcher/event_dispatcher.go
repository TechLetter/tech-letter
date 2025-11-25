package dispatcher

import (
	"context"
	"fmt"
	"time"

	"tech-letter/eventbus"
	"tech-letter/events"
	"tech-letter/models"

	"github.com/google/uuid"
)

// EventDispatcher Aggregate용 이벤트 발행 서비스
type EventDispatcher struct {
	bus eventbus.EventBus
}

// NewEventDispatcher 새로운 이벤트 디스패처 생성
func NewEventDispatcher(bus eventbus.EventBus) *EventDispatcher {
	return &EventDispatcher{
		bus: bus,
	}
}

// PublishPostCreated 새 포스트 생성 이벤트 발행
func (s *EventDispatcher) PublishPostCreated(ctx context.Context, post *models.Post) error {
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
