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

const (
	// 재시도 관련 상수
	MaxRetryCount     = 3
	RetryDelaySeconds = 300 // 5분
)

// RetryMetadata 재시도 메타데이터 (Kafka 헤더에 저장)
type RetryMetadata struct {
	RetryCount   int       `json:"retry_count"`
	OriginalTime time.Time `json:"original_time"`
	LastError    string    `json:"last_error"`
	RetryAfter   time.Time `json:"retry_after"` // 재시도 가능 시간
}

// RetryKafkaConsumer 재시도 기능이 있는 Consumer (Consumer 인터페이스 구현)
type RetryKafkaConsumer struct {
	consumer       *kafka.Consumer
	retryConsumer  *kafka.Consumer // 재시도 토픽 전용 Consumer
	handlers       map[events.EventType]EventHandler
	producer       Producer
	mainTopic      string
	retryTopicName string
}

// NewRetryConsumer 재시도 기능이 있는 Consumer 생성
func NewRetryConsumer(kafkaConfig *Config, producer Producer) (Consumer, error) {
	if kafkaConfig == nil {
		return nil, fmt.Errorf("kafka config is required")
	}

	// 메인 토픽용 Consumer
	consumerConfig := kafkaConfig.ConsumerConfig()
	consumer, err := kafka.NewConsumer(&consumerConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create kafka consumer: %w", err)
	}

	// 재시도 토픽용 Consumer (별도 그룹)
	retryConsumerConfig := kafkaConfig.ConsumerConfig()
	retryConsumerConfig["group.id"] = kafkaConfig.GroupID + "-retry"
	retryConsumer, err := kafka.NewConsumer(&retryConsumerConfig)
	if err != nil {
		consumer.Close()
		return nil, fmt.Errorf("failed to create retry consumer: %w", err)
	}

	return &RetryKafkaConsumer{
		consumer:       consumer,
		retryConsumer:  retryConsumer,
		handlers:       make(map[events.EventType]EventHandler),
		producer:       producer,
		retryTopicName: TopicPostEventsRetry,
	}, nil
}

// Subscribe 토픽 구독
func (c *RetryKafkaConsumer) Subscribe(topics []string) error {
	// 메인 토픽 구독
	err := c.consumer.SubscribeTopics(topics, nil)
	if err != nil {
		return fmt.Errorf("failed to subscribe to topics: %w", err)
	}
	c.mainTopic = topics[0] // 첫 번째 토픽을 메인으로 설정

	// 재시도 토픽 구독
	err = c.retryConsumer.SubscribeTopics([]string{c.retryTopicName}, nil)
	if err != nil {
		return fmt.Errorf("failed to subscribe to retry topic: %w", err)
	}

	config.Logger.Infof("subscribed to main topics: %v", topics)
	config.Logger.Infof("subscribed to retry topic: %s", c.retryTopicName)
	return nil
}

// RegisterHandler 이벤트 타입별 핸들러 등록
func (c *RetryKafkaConsumer) RegisterHandler(eventType events.EventType, handler EventHandler) {
	c.handlers[eventType] = handler
	config.Logger.Infof("registered handler for event type: %s", eventType)
}

// Close 컨슈머 종료
func (c *RetryKafkaConsumer) Close() error {
	if err := c.consumer.Close(); err != nil {
		return fmt.Errorf("failed to close main consumer: %w", err)
	}
	if err := c.retryConsumer.Close(); err != nil {
		return fmt.Errorf("failed to close retry consumer: %w", err)
	}
	config.Logger.Info("kafka consumer with retry closed")
	return nil
}

// processMessage 메시지 처리 (재시도 로직 포함)
func (c *RetryKafkaConsumer) processMessageWithRetry(ctx context.Context, msg *kafka.Message) error {
	// 재시도 메타데이터 추출
	retryMeta := c.extractRetryMetadata(msg)

	// 재시도 토픽에서 온 메시지인 경우 시간 체크
	if *msg.TopicPartition.Topic == c.retryTopicName {
		if time.Now().Before(retryMeta.RetryAfter) {
			// 아직 재시도 시간이 안 됨 - 무시 (다음 폴링에서 다시 처리)
			config.Logger.Debugf("message not ready for retry, waiting...")
			return nil
		}
		// 시간이 됨 - 메인 토픽으로 다시 발행
		c.moveToMainTopic(msg, retryMeta)
		return nil
	}

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
	event, err := events.DeserializeEvent(eventType, msg.Value)
	if err != nil {
		return fmt.Errorf("failed to deserialize event: %w", err)
	}

	// 핸들러 실행
	if err := handler(ctx, event); err != nil {
		config.Logger.Errorf("handler failed for event type %s: %v", eventType, err)

		// 재시도 처리
		if retryMeta.RetryCount < MaxRetryCount {
			c.scheduleRetry(msg, retryMeta, err)
			return nil // 재시도 예약 성공
		} else {
			// 최대 재시도 초과 - DLQ로 전송
			c.sendToDLQ(msg, retryMeta, err)
			return fmt.Errorf("max retry count exceeded, sent to DLQ")
		}
	}

	config.Logger.Debugf("successfully processed event: %s", eventType)
	return nil
}

// extractRetryMetadata 메시지에서 재시도 메타데이터 추출
func (c *RetryKafkaConsumer) extractRetryMetadata(msg *kafka.Message) RetryMetadata {
	meta := RetryMetadata{
		RetryCount:   0,
		OriginalTime: time.Now(),
	}

	for _, header := range msg.Headers {
		if header.Key == "retry-metadata" {
			if err := json.Unmarshal(header.Value, &meta); err != nil {
				config.Logger.Warnf("failed to parse retry metadata: %v", err)
			}
			break
		}
	}

	return meta
}

// scheduleRetry 재시도 예약 (재시도 토픽으로 발행)
func (c *RetryKafkaConsumer) scheduleRetry(msg *kafka.Message, meta RetryMetadata, lastErr error) {
	meta.RetryCount++
	meta.LastError = lastErr.Error()
	meta.RetryAfter = time.Now().Add(time.Duration(RetryDelaySeconds) * time.Second)

	metaBytes, err := json.Marshal(meta)
	if err != nil {
		config.Logger.Errorf("failed to marshal retry metadata: %v", err)
		return
	}

	// 기존 헤더 복사 + 재시도 메타데이터 추가
	headers := make([]kafka.Header, 0, len(msg.Headers)+1)
	for _, h := range msg.Headers {
		if h.Key != "retry-metadata" { // 기존 retry-metadata는 제외
			headers = append(headers, h)
		}
	}
	headers = append(headers, kafka.Header{
		Key:   "retry-metadata",
		Value: metaBytes,
	})

	// 재시도 토픽으로 발행
	retryTopic := c.retryTopicName
	retryMsg := &kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &retryTopic, Partition: kafka.PartitionAny},
		Value:          msg.Value,
		Headers:        headers,
		Timestamp:      time.Now(),
	}

	kafkaProducer, ok := c.producer.(*KafkaProducer)
	if !ok {
		config.Logger.Errorf("invalid producer type")
		return
	}

	if err := kafkaProducer.producer.Produce(retryMsg, nil); err != nil {
		config.Logger.Errorf("failed to schedule retry: %v", err)
	} else {
		config.Logger.Infof("scheduled retry %d/%d to retry topic, will process after %d seconds", 
			meta.RetryCount, MaxRetryCount, RetryDelaySeconds)
	}
}

// moveToMainTopic 재시도 토픽에서 메인 토픽으로 메시지 이동
func (c *RetryKafkaConsumer) moveToMainTopic(msg *kafka.Message, meta RetryMetadata) {
	// 메인 토픽으로 다시 발행
	mainTopic := c.mainTopic
	mainMsg := &kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &mainTopic, Partition: kafka.PartitionAny},
		Value:          msg.Value,
		Headers:        msg.Headers, // 메타데이터 그대로 유지
		Timestamp:      time.Now(),
	}

	kafkaProducer, ok := c.producer.(*KafkaProducer)
	if !ok {
		config.Logger.Errorf("invalid producer type")
		return
	}

	if err := kafkaProducer.producer.Produce(mainMsg, nil); err != nil {
		config.Logger.Errorf("failed to move message to main topic: %v", err)
	} else {
		config.Logger.Infof("moved message from retry topic to main topic for retry %d", meta.RetryCount)
	}
}

// sendToDLQ DLQ로 메시지 전송
func (c *RetryKafkaConsumer) sendToDLQ(msg *kafka.Message, meta RetryMetadata, lastErr error) {
	meta.LastError = lastErr.Error()

	metaBytes, err := json.Marshal(meta)
	if err != nil {
		config.Logger.Errorf("failed to marshal DLQ metadata: %v", err)
		return
	}

	headers := append(msg.Headers, kafka.Header{
		Key:   "dlq-metadata",
		Value: metaBytes,
	})

	dlqTopic := TopicPostEventsDLQ
	dlqMsg := &kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &dlqTopic, Partition: kafka.PartitionAny},
		Value:          msg.Value,
		Headers:        headers,
		Timestamp:      time.Now(),
	}

	kafkaProducer, ok := c.producer.(*KafkaProducer)
	if !ok {
		config.Logger.Errorf("invalid producer type")
		return
	}

	if err := kafkaProducer.producer.Produce(dlqMsg, nil); err != nil {
		config.Logger.Errorf("failed to send to DLQ: %v", err)
	} else {
		config.Logger.Warnf("message sent to DLQ after %d retries", meta.RetryCount)
	}
}

// Start Consumer 시작 (재시도 로직 포함)
func (c *RetryKafkaConsumer) Start(ctx context.Context) error {
	config.Logger.Info("starting kafka consumer with retry...")

	for {
		select {
		case <-ctx.Done():
			config.Logger.Info("kafka consumer context cancelled")
			return ctx.Err()
		default:
			// 메인 토픽 폴링
			msg, err := c.consumer.ReadMessage(50 * time.Millisecond)
			if err == nil {
				if err := c.processMessageWithRetry(ctx, msg); err != nil {
					config.Logger.Errorf("failed to process main message: %v", err)
				}
				continue
			} else if err.(kafka.Error).Code() != kafka.ErrTimedOut {
				config.Logger.Errorf("main consumer error: %v", err)
			}

			// 재시도 토픽 폴링
			retryMsg, err := c.retryConsumer.ReadMessage(50 * time.Millisecond)
			if err == nil {
				if err := c.processMessageWithRetry(ctx, retryMsg); err != nil {
					config.Logger.Errorf("failed to process retry message: %v", err)
				}
				continue
			} else if err.(kafka.Error).Code() != kafka.ErrTimedOut {
				config.Logger.Errorf("retry consumer error: %v", err)
			}
		}
	}
}
