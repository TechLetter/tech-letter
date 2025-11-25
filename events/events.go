package events

import (
	"encoding/json"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// EventType 이벤트 타입 정의
type EventType string

const (
	PostCreated    EventType = "post.created"
	PostSummarized EventType = "post.summarized"
)

// BaseEvent 모든 이벤트의 기본 구조
type BaseEvent struct {
	ID        string    `json:"id"`
	Type      EventType `json:"type"`
	Timestamp time.Time `json:"timestamp"`
	Source    string    `json:"source"`
	Version   string    `json:"version"`
}

// PostCreatedEvent 포스트 생성 이벤트 (파이프라인 시작)
type PostCreatedEvent struct {
	BaseEvent
	PostID   primitive.ObjectID `json:"post_id"`
	BlogID   primitive.ObjectID `json:"blog_id"`
	BlogName string             `json:"blog_name"`
	Title    string             `json:"title"`
	Link     string             `json:"link"`
}

// PostSummarizedEvent AI 요약 완료 이벤트
type PostSummarizedEvent struct {
	BaseEvent
	PostID       primitive.ObjectID `json:"post_id"`
	Link         string             `json:"link"`
	RenderedHTML string             `json:"rendered_html"`
	ThumbnailURL string             `json:"thumbnail_url"`
	Categories   []string           `json:"categories"`
	Tags         []string           `json:"tags"`
	Summary      string             `json:"summary"`
	ModelName    string             `json:"model_name"`
}

// SerializeEvent 이벤트를 JSON으로 직렬화하고 타입 정보 반환
func SerializeEvent(event interface{}) ([]byte, EventType, error) {
	var eventType EventType

	switch e := event.(type) {
	case PostCreatedEvent:
		eventType = e.Type
	case PostSummarizedEvent:
		eventType = e.Type
	default:
		return nil, "", fmt.Errorf("unknown event type: %T", event)
	}

	data, err := json.Marshal(event)
	if err != nil {
		return nil, "", fmt.Errorf("failed to marshal event: %w", err)
	}

	return data, eventType, nil
}

// DeserializeEvent 이벤트 타입에 따라 적절한 구조체로 역직렬화
func DeserializeEvent(eventType EventType, data []byte) (interface{}, error) {
	var event interface{}

	switch eventType {
	case PostCreated:
		event = &PostCreatedEvent{}
	case PostSummarized:
		event = &PostSummarizedEvent{}
	default:
		return nil, fmt.Errorf("unknown event type: %s", eventType)
	}

	if err := json.Unmarshal(data, event); err != nil {
		return nil, fmt.Errorf("failed to unmarshal event: %w", err)
	}

	return event, nil
}
