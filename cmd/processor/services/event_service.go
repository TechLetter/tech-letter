package services

import (
	"context"
	"time"

	"tech-letter/events"
	"tech-letter/kafka"
	"tech-letter/models"

	"github.com/google/uuid"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

// EventService Processor용 이벤트 발행 서비스
type EventService struct {
	producer kafka.Producer
}

// NewEventService 새로운 이벤트 서비스 생성
func NewEventService(producer kafka.Producer) *EventService {
	return &EventService{
		producer: producer,
	}
}

// PublishPostHTMLFetched HTML 렌더링 완료 이벤트 발행
func (s *EventService) PublishPostHTMLFetched(ctx context.Context, postID primitive.ObjectID, link string) error {
	event := events.PostHTMLFetchedEvent{
		BaseEvent: events.BaseEvent{
			ID:        uuid.New().String(),
			Type:      events.PostHTMLFetched,
			Timestamp: time.Now(),
			Source:    "processor",
			Version:   "1.0",
		},
		PostID: postID,
		Link:   link,
	}

	return s.producer.PublishEvent(kafka.TopicPostEvents, event)
}

// PublishPostTextParsed 텍스트 파싱 완료 이벤트 발행
func (s *EventService) PublishPostTextParsed(ctx context.Context, postID primitive.ObjectID, link, thumbnailURL string) error {
	event := events.PostTextParsedEvent{
		BaseEvent: events.BaseEvent{
			ID:        uuid.New().String(),
			Type:      events.PostTextParsed,
			Timestamp: time.Now(),
			Source:    "processor",
			Version:   "1.0",
		},
		PostID:       postID,
		Link:         link,
		ThumbnailURL: thumbnailURL,
	}

	return s.producer.PublishEvent(kafka.TopicPostEvents, event)
}

// PublishPostSummarized AI 요약 완료 이벤트 발행
func (s *EventService) PublishPostSummarized(ctx context.Context, postID primitive.ObjectID, link string, summary models.AISummary) error {
	event := events.PostSummarizedEvent{
		BaseEvent: events.BaseEvent{
			ID:        uuid.New().String(),
			Type:      events.PostSummarized,
			Timestamp: time.Now(),
			Source:    "processor",
			Version:   "1.0",
		},
		PostID:     postID,
		Link:       link,
		Categories: summary.Categories,
		Tags:       summary.Tags,
		Summary:    summary.Summary,
		ModelName:  summary.ModelName,
	}

	return s.producer.PublishEvent(kafka.TopicPostEvents, event)
}
