package services

import (
	"context"
	"time"

	"tech-letter/events"
	"tech-letter/kafka"
	"tech-letter/models"

	"github.com/google/uuid"
)

// EventService Aggregate용 이벤트 발행 서비스
type EventService struct {
	producer kafka.Producer
}

// NewEventService 새로운 이벤트 서비스 생성
func NewEventService(producer kafka.Producer) *EventService {
	return &EventService{
		producer: producer,
	}
}

// PublishPostCreated 포스트 생성 이벤트 발행
func (s *EventService) PublishPostCreated(ctx context.Context, post *models.Post) error {
	event := events.PostCreatedEvent{
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

	return s.producer.PublishEvent(kafka.TopicPostEvents, event)
}
