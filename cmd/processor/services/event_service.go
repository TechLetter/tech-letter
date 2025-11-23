package services

import (
	"context"
	"fmt"
	"time"

	"tech-letter/eventbus"
	"tech-letter/events"
	"tech-letter/models"

	"github.com/google/uuid"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

// EventService Processor용 이벤트 발행 서비스
type EventService struct {
	bus eventbus.EventBus
}

// NewEventService 새로운 이벤트 서비스 생성
func NewEventService(bus eventbus.EventBus) *EventService {
	return &EventService{
		bus: bus,
	}
}

// PublishPostSummarized AI 요약 완료 이벤트 발행
func (s *EventService) PublishPostSummarized(ctx context.Context, postID primitive.ObjectID, link, thumbnailURL string, summary models.AISummary) error {
	e := events.PostSummarizedEvent{
		BaseEvent: events.BaseEvent{
			ID:        uuid.New().String(),
			Type:      events.PostSummarized,
			Timestamp: time.Now(),
			Source:    "processor",
			Version:   "1.0",
		},
		PostID:       postID,
		Link:         link,
		ThumbnailURL: thumbnailURL,
		Categories:   summary.Categories,
		Tags:         summary.Tags,
		Summary:      summary.Summary,
		ModelName:    summary.ModelName,
	}
	evt, err := eventbus.NewJSONEvent("", e, 0)
	if err != nil {
		return fmt.Errorf("failed to build event: %w", err)
	}
	return s.bus.Publish(ctx, eventbus.TopicPostEvents.Base(), evt)
}
