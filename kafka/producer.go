package kafka

import (
	"fmt"
	"time"

	"tech-letter/config"
	"tech-letter/events"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

// Producer Kafka 프로듀서 인터페이스
type Producer interface {
	PublishEvent(topic string, event interface{}) error
	Close() error
}

// KafkaProducer Kafka 프로듀서 구현체
type KafkaProducer struct {
	producer *kafka.Producer
}

// NewProducer 새로운 Kafka 프로듀서 생성
func NewProducer(kafkaConfig *Config) (*KafkaProducer, error) {
	if kafkaConfig == nil {
		return nil, fmt.Errorf("kafka config is required")
	}
	
	producerConfig := kafkaConfig.ProducerConfig()

	producer, err := kafka.NewProducer(&producerConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create kafka producer: %w", err)
	}

	// 백그라운드에서 delivery report 처리
	go func() {
		for e := range producer.Events() {
			switch ev := e.(type) {
			case *kafka.Message:
				if ev.TopicPartition.Error != nil {
					config.Logger.Errorf("delivery failed: %v", ev.TopicPartition.Error)
				} else {
					config.Logger.Debugf("delivered message to %v", ev.TopicPartition)
				}
			}
		}
	}()

	return &KafkaProducer{producer: producer}, nil
}

// PublishEvent 이벤트를 지정된 토픽에 발행
func (p *KafkaProducer) PublishEvent(topic string, event interface{}) error {
	// Events 패키지를 사용하여 직렬화
	eventBytes, eventType, err := events.SerializeEvent(event)
	if err != nil {
		return fmt.Errorf("failed to serialize event: %w", err)
	}

	// 메시지 생성 및 발행
	message := &kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
		Value:          eventBytes,
		Timestamp:      time.Now(),
		Headers: []kafka.Header{
			{Key: "event-type", Value: []byte(eventType)},
		},
	}

	err = p.producer.Produce(message, nil)
	if err != nil {
		return fmt.Errorf("failed to produce message: %w", err)
	}

	config.Logger.Debugf("published event %s to topic %s", eventType, topic)
	return nil
}

// Close 프로듀서 종료
func (p *KafkaProducer) Close() error {
	// 대기 중인 메시지들이 모두 전송될 때까지 최대 10초 대기
	p.producer.Flush(10 * 1000)
	p.producer.Close()
	return nil
}

// 토픽 상수 정의
const (
	TopicPostEvents       = "tech-letter.post.events"
	TopicNewsletterEvents = "tech-letter.newsletter.events"
)
