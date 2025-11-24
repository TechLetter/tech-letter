package services

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"

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

// PublishPostCreated 새 포스트 생성 이벤트 발행
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

// PublishPostContentParsed 본문 파싱 완료 이벤트 발행 (Aggregate -> Processor, RenderedHTML 포함)
func (s *EventService) PublishPostContentParsed(ctx context.Context, postID primitive.ObjectID, link, renderedHTML string) error {
	e := events.PostContentParsedEvent{
		BaseEvent: events.BaseEvent{
			ID:        uuid.New().String(),
			Type:      events.PostContentParsed,
			Timestamp: time.Now(),
			Source:    "aggregate",
			Version:   "1.0",
		},
		PostID:       postID,
		Link:         link,
		RenderedHTML: renderedHTML,
	}

	evt, err := eventbus.NewJSONEvent("", e, 0)
	if err != nil {
		return fmt.Errorf("failed to build event: %w", err)
	}
	return s.bus.Publish(ctx, eventbus.TopicPostEvents.Base(), evt)
}

// PublishPostHTMLRendered HTML 렌더링 완료 이벤트 발행 (재발행용, Aggregate -> Aggregate)
func (s *EventService) PublishPostHTMLRendered(ctx context.Context, postID primitive.ObjectID, link, renderedHTML string) error {
e := events.PostHTMLRenderedEvent{
BaseEvent: events.BaseEvent{
ID:        uuid.New().String(),
Type:      events.PostHTMLRendered,
Timestamp: time.Now(),
Source:    "aggregate",
Version:   "1.0",
},
PostID:       postID,
Link:         link,
RenderedHTML: renderedHTML,
ThumbnailURL: "", // 재파싱 시 썸네일은 Processor가 다시 추출
}

evt, err := eventbus.NewJSONEvent("", e, 0)
if err != nil {
return fmt.Errorf("failed to build event: %w", err)
}
return s.bus.Publish(ctx, eventbus.TopicPostEvents.Base(), evt)
}

// PublishPostThumbnailParseRequested 썸네일 파싱 요청 이벤트 발행 (Aggregate -> Processor)
func (s *EventService) PublishPostThumbnailParseRequested(ctx context.Context, postID primitive.ObjectID, link, renderedHTML string) error {
e := events.PostThumbnailParseRequestedEvent{
BaseEvent: events.BaseEvent{
ID:        uuid.New().String(),
Type:      events.PostThumbnailParseRequested,
Timestamp: time.Now(),
Source:    "aggregate",
Version:   "1.0",
},
PostID:       postID,
Link:         link,
RenderedHTML: renderedHTML,
}

evt, err := eventbus.NewJSONEvent("", e, 0)
if err != nil {
return fmt.Errorf("failed to build event: %w", err)
}
return s.bus.Publish(ctx, eventbus.TopicPostEvents.Base(), evt)
}
