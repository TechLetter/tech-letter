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
	PostCreated         EventType = "post.created"
	PostHTMLFetched     EventType = "post.html_fetched"
	PostTextParsed      EventType = "post.text_parsed"
	PostSummarized      EventType = "post.summarized"
	NewsletterRequested EventType = "newsletter.requested"
	NewsletterGenerated EventType = "newsletter.generated"
	NewsletterSent      EventType = "newsletter.sent"
)

// BaseEvent 모든 이벤트의 기본 구조
type BaseEvent struct {
	ID        string    `json:"id"`
	Type      EventType `json:"type"`
	Timestamp time.Time `json:"timestamp"`
	Source    string    `json:"source"`
	Version   string    `json:"version"`
}

// PostCreatedEvent 포스트 생성 이벤트
type PostCreatedEvent struct {
	BaseEvent
	PostID   primitive.ObjectID `json:"post_id"`
	BlogID   primitive.ObjectID `json:"blog_id"`
	BlogName string             `json:"blog_name"`
	Title    string             `json:"title"`
	Link     string             `json:"link"`
}

// PostHTMLFetchedEvent HTML 렌더링 완료 이벤트
type PostHTMLFetchedEvent struct {
	BaseEvent
	PostID primitive.ObjectID `json:"post_id"`
	Link   string             `json:"link"`
}

// PostTextParsedEvent 텍스트 파싱 완료 이벤트
type PostTextParsedEvent struct {
	BaseEvent
	PostID       primitive.ObjectID `json:"post_id"`
	Link         string             `json:"link"`
	ThumbnailURL string             `json:"thumbnail_url"`
}

// PostSummarizedEvent AI 요약 완료 이벤트
type PostSummarizedEvent struct {
	BaseEvent
	PostID     primitive.ObjectID `json:"post_id"`
	Link       string             `json:"link"`
	Categories []string           `json:"categories"`
	Tags       []string           `json:"tags"`
	Summary    string             `json:"summary"`
	ModelName  string             `json:"model_name"`
}

// DateRange 날짜 범위
type DateRange struct {
	StartDate time.Time `json:"start_date"`
	EndDate   time.Time `json:"end_date"`
}

// NewsletterRequestedEvent 뉴스레터 요청 이벤트
type NewsletterRequestedEvent struct {
	BaseEvent
	RequestID   string    `json:"request_id"`
	RequestedBy string    `json:"requested_by"`
	DateRange   DateRange `json:"date_range"`
	Categories  []string  `json:"categories"`
}

// NewsletterGeneratedEvent 뉴스레터 생성 완료 이벤트
type NewsletterGeneratedEvent struct {
	BaseEvent
	RequestID string `json:"request_id"`
	Content   string `json:"content"`
}

// NewsletterSentEvent 뉴스레터 발송 완료 이벤트
type NewsletterSentEvent struct {
	BaseEvent
	RequestID string `json:"request_id"`
	SentTo    string `json:"sent_to"`
}

// SerializeEvent 이벤트를 JSON으로 직렬화하고 타입 정보 반환
func SerializeEvent(event interface{}) ([]byte, EventType, error) {
	var eventType EventType
	
	switch e := event.(type) {
	case PostCreatedEvent:
		eventType = e.Type
	case PostHTMLFetchedEvent:
		eventType = e.Type
	case PostTextParsedEvent:
		eventType = e.Type
	case PostSummarizedEvent:
		eventType = e.Type
	case NewsletterRequestedEvent:
		eventType = e.Type
	case NewsletterGeneratedEvent:
		eventType = e.Type
	case NewsletterSentEvent:
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
	case PostHTMLFetched:
		event = &PostHTMLFetchedEvent{}
	case PostTextParsed:
		event = &PostTextParsedEvent{}
	case PostSummarized:
		event = &PostSummarizedEvent{}
	case NewsletterRequested:
		event = &NewsletterRequestedEvent{}
	case NewsletterGenerated:
		event = &NewsletterGeneratedEvent{}
	case NewsletterSent:
		event = &NewsletterSentEvent{}
	default:
		return nil, fmt.Errorf("unknown event type: %s", eventType)
	}

	if err := json.Unmarshal(data, event); err != nil {
		return nil, fmt.Errorf("failed to unmarshal event: %w", err)
	}

	return event, nil
}
