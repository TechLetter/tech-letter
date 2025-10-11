package kafka

import (
	"context"

	"tech-letter/events"
)

// EventHandler 이벤트 처리 함수 타입
type EventHandler func(ctx context.Context, event interface{}) error

// Consumer Kafka 컨슈머 인터페이스
type Consumer interface {
	Subscribe(topics []string) error
	RegisterHandler(eventType events.EventType, handler EventHandler)
	Start(ctx context.Context) error
	Close() error
}
