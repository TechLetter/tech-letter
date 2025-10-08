package kafka

import (
	"os"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

// Config Kafka 설정 구조체
type Config struct {
	BootstrapServers string
	GroupID          string
	AutoOffsetReset  string
}

// 기본값 상수 정의
const (
	DefaultAutoOffsetReset = "earliest"

	// Producer 기본값
	DefaultProducerAcks      = "all"
	DefaultProducerRetries   = 3
	DefaultProducerBatchSize = 16384
	DefaultProducerLingerMs  = 10

	// Consumer 기본값
	DefaultConsumerEnableAutoCommit = true
	DefaultConsumerSessionTimeoutMs = 6000
)

// NewConfig 환경변수에서 Kafka 설정을 생성
func NewConfig() *Config {
	bootstrapServers := os.Getenv("KAFKA_BOOTSTRAP_SERVERS")
	if bootstrapServers == "" {
		panic("KAFKA_BOOTSTRAP_SERVERS environment variable is required")
	}

	groupID := os.Getenv("KAFKA_GROUP_ID")
	if groupID == "" {
		panic("KAFKA_GROUP_ID environment variable is required")
	}

	return &Config{
		BootstrapServers: bootstrapServers,
		GroupID:          groupID,
		AutoOffsetReset:  getEnv("KAFKA_AUTO_OFFSET_RESET", DefaultAutoOffsetReset),
	}
}

// ProducerConfig Producer 설정을 반환
func (c *Config) ProducerConfig() kafka.ConfigMap {
	return kafka.ConfigMap{
		"bootstrap.servers": c.BootstrapServers,
		"acks":              DefaultProducerAcks,
		"retries":           DefaultProducerRetries,
		"batch.size":        DefaultProducerBatchSize,
		"linger.ms":         DefaultProducerLingerMs,
	}
}

// ConsumerConfig Consumer 설정을 반환
func (c *Config) ConsumerConfig() kafka.ConfigMap {
	return kafka.ConfigMap{
		"bootstrap.servers":  c.BootstrapServers,
		"group.id":           c.GroupID,
		"auto.offset.reset":  c.AutoOffsetReset,
		"enable.auto.commit": DefaultConsumerEnableAutoCommit,
		"session.timeout.ms": DefaultConsumerSessionTimeoutMs,
	}
}

// getEnv 환경변수를 가져오되, 없으면 기본값 반환
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
