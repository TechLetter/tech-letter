package kafka

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"tech-letter/config"
	"tech-letter/events"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
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

// KafkaConsumer Kafka 컨슈머 구현체
type KafkaConsumer struct {
	consumer *kafka.Consumer
	handlers map[events.EventType]EventHandler
}

// NewConsumer 새로운 Kafka 컨슈머 생성
func NewConsumer(kafkaConfig *Config) (*KafkaConsumer, error) {
	if kafkaConfig == nil {
		return nil, fmt.Errorf("kafka config is required")
	}
	
	consumerConfig := kafkaConfig.ConsumerConfig()

	consumer, err := kafka.NewConsumer(&consumerConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create kafka consumer: %w", err)
	}

	return &KafkaConsumer{
		consumer: consumer,
		handlers: make(map[events.EventType]EventHandler),
	}, nil
}

// Subscribe 토픽 구독
func (c *KafkaConsumer) Subscribe(topics []string) error {
	err := c.consumer.SubscribeTopics(topics, nil)
	if err != nil {
		return fmt.Errorf("failed to subscribe to topics: %w", err)
	}

	config.Logger.Infof("subscribed to topics: %v", topics)
	return nil
}

// RegisterHandler 이벤트 타입별 핸들러 등록
func (c *KafkaConsumer) RegisterHandler(eventType events.EventType, handler EventHandler) {
	c.handlers[eventType] = handler
	config.Logger.Infof("registered handler for event type: %s", eventType)
}

// Start 컨슈머 시작
func (c *KafkaConsumer) Start(ctx context.Context) error {
	config.Logger.Info("starting kafka consumer...")

	for {
		select {
		case <-ctx.Done():
			config.Logger.Info("kafka consumer context cancelled")
			return ctx.Err()
		default:
			msg, err := c.consumer.ReadMessage(100 * time.Millisecond)
			if err != nil {
				if err.(kafka.Error).Code() == kafka.ErrTimedOut {
					continue
				}
				config.Logger.Errorf("consumer error: %v", err)
				continue
			}

			if err := c.processMessage(ctx, msg); err != nil {
				config.Logger.Errorf("failed to process message: %v", err)
				// 에러가 발생해도 계속 진행 (메시지 손실 방지)
			}
		}
	}
}

// processMessage 메시지 처리
func (c *KafkaConsumer) processMessage(ctx context.Context, msg *kafka.Message) error {
	// 이벤트 타입 추출
	var eventType events.EventType
	for _, header := range msg.Headers {
		if header.Key == "event-type" {
			eventType = events.EventType(header.Value)
			break
		}
	}

	if eventType == "" {
		return fmt.Errorf("event-type header not found")
	}

	// 등록된 핸들러 찾기
	handler, exists := c.handlers[eventType]
	if !exists {
		config.Logger.Warnf("no handler registered for event type: %s", eventType)
		return nil
	}

	// 이벤트 역직렬화
	event, err := c.deserializeEvent(eventType, msg.Value)
	if err != nil {
		return fmt.Errorf("failed to deserialize event: %w", err)
	}

	// 핸들러 실행
	if err := handler(ctx, event); err != nil {
		return fmt.Errorf("handler failed for event type %s: %w", eventType, err)
	}

	config.Logger.Debugf("successfully processed event: %s", eventType)
	return nil
}

// deserializeEvent 이벤트 타입에 따라 적절한 구조체로 역직렬화
func (c *KafkaConsumer) deserializeEvent(eventType events.EventType, data []byte) (interface{}, error) {
	var event interface{}

	switch eventType {
	case events.PostCreated:
		event = &events.PostCreatedEvent{}
	case events.PostHTMLFetched:
		event = &events.PostHTMLFetchedEvent{}
	case events.PostTextParsed:
		event = &events.PostTextParsedEvent{}
	case events.PostSummarized:
		event = &events.PostSummarizedEvent{}
	case events.NewsletterRequested:
		event = &events.NewsletterRequestedEvent{}
	case events.NewsletterGenerated:
		event = &events.NewsletterGeneratedEvent{}
	case events.NewsletterSent:
		event = &events.NewsletterSentEvent{}
	default:
		return nil, fmt.Errorf("unknown event type: %s", eventType)
	}

	if err := json.Unmarshal(data, event); err != nil {
		return nil, fmt.Errorf("failed to unmarshal event: %w", err)
	}

	return event, nil
}

// Close 컨슈머 종료
func (c *KafkaConsumer) Close() error {
	if err := c.consumer.Close(); err != nil {
		return fmt.Errorf("failed to close consumer: %w", err)
	}
	config.Logger.Info("kafka consumer closed")
	return nil
}
