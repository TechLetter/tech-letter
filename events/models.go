package events

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// EventType 이벤트 타입을 정의하는 열거형
type EventType string

const (
	// 포스트 관련 이벤트
	PostCreated     EventType = "post.created"
	PostHTMLFetched EventType = "post.html_fetched"
	PostTextParsed  EventType = "post.text_parsed"
	PostSummarized  EventType = "post.summarized"

	// 뉴스레터 관련 이벤트 (Phase 2)
	NewsletterRequested EventType = "newsletter.requested"
	NewsletterGenerated EventType = "newsletter.generated"
	NewsletterSent      EventType = "newsletter.sent"
)

// BaseEvent 모든 이벤트의 기본 구조
type BaseEvent struct {
	ID        string    `json:"id"`
	Type      EventType `json:"type"`
	Timestamp time.Time `json:"timestamp"`
	Source    string    `json:"source"` // "aggregate", "api", "newsletter" 등
	Version   string    `json:"version"`
}

// GetType 이벤트 타입을 반환
func (e BaseEvent) GetType() EventType {
	return e.Type
}

// PostCreatedEvent 새 포스트가 생성되었을 때 발행되는 이벤트
type PostCreatedEvent struct {
	BaseEvent
	PostID   primitive.ObjectID `json:"post_id"`
	BlogID   primitive.ObjectID `json:"blog_id"`
	BlogName string             `json:"blog_name"`
	Title    string             `json:"title"`
	Link     string             `json:"link"`
}

// PostHTMLFetchedEvent HTML 렌더링이 완료되었을 때 발행되는 이벤트
type PostHTMLFetchedEvent struct {
	BaseEvent
	PostID primitive.ObjectID `json:"post_id"`
	Link   string             `json:"link"`
}

// PostTextParsedEvent 텍스트 파싱이 완료되었을 때 발행되는 이벤트
type PostTextParsedEvent struct {
	BaseEvent
	PostID       primitive.ObjectID `json:"post_id"`
	Link         string             `json:"link"`
	ThumbnailURL string             `json:"thumbnail_url,omitempty"`
}

// PostSummarizedEvent AI 요약이 완료되었을 때 발행되는 이벤트
type PostSummarizedEvent struct {
	BaseEvent
	PostID     primitive.ObjectID `json:"post_id"`
	Link       string             `json:"link"`
	Categories []string           `json:"categories"`
	Tags       []string           `json:"tags"`
	Summary    string             `json:"summary"`
	ModelName  string             `json:"model_name"`
}

// NewsletterRequestedEvent 뉴스레터 발송 요청 이벤트 (Phase 2)
type NewsletterRequestedEvent struct {
	BaseEvent
	RequestID   string    `json:"request_id"`
	RequestedBy string    `json:"requested_by"` // "admin", "scheduler" 등
	DateRange   DateRange `json:"date_range"`
	Categories  []string  `json:"categories,omitempty"`
}

// DateRange 날짜 범위를 나타내는 구조체
type DateRange struct {
	From time.Time `json:"from"`
	To   time.Time `json:"to"`
}

// NewsletterGeneratedEvent 뉴스레터 생성 완료 이벤트 (Phase 2)
type NewsletterGeneratedEvent struct {
	BaseEvent
	RequestID    string               `json:"request_id"`
	PostCount    int                  `json:"post_count"`
	PostIDs      []primitive.ObjectID `json:"post_ids"`
	HTMLContent  string               `json:"html_content"`
	TextContent  string               `json:"text_content"`
	Subject      string               `json:"subject"`
	GeneratedAt  time.Time            `json:"generated_at"`
}

// NewsletterSentEvent 뉴스레터 발송 완료 이벤트 (Phase 2)
type NewsletterSentEvent struct {
	BaseEvent
	RequestID      string    `json:"request_id"`
	RecipientCount int       `json:"recipient_count"`
	SentAt         time.Time `json:"sent_at"`
	Provider       string    `json:"provider"` // "sendgrid", "ses" 등
}
