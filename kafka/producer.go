package kafka

// Producer Kafka 프로듀서 인터페이스
type Producer interface {
	PublishEvent(topic string, event interface{}) error
	Close() error
}
