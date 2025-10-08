package kafka

import (
	"context"
	"fmt"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"tech-letter/config"
)

// CreateTopicsIfNotExists 토픽이 존재하지 않으면 생성
func CreateTopicsIfNotExists(kafkaConfig *Config) error {
	if kafkaConfig == nil {
		return fmt.Errorf("kafka config is required")
	}

	adminClient, err := kafka.NewAdminClient(&kafka.ConfigMap{
		"bootstrap.servers": kafkaConfig.BootstrapServers,
	})
	if err != nil {
		return fmt.Errorf("failed to create admin client: %w", err)
	}
	defer adminClient.Close()

	// 생성할 토픽 목록
	topics := []kafka.TopicSpecification{
		{
			Topic:             TopicPostEvents,
			NumPartitions:     3,
			ReplicationFactor: 1,
		},
		{
			Topic:             TopicNewsletterEvents,
			NumPartitions:     3,
			ReplicationFactor: 1,
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// 토픽 생성 시도
	results, err := adminClient.CreateTopics(ctx, topics)
	if err != nil {
		return fmt.Errorf("failed to create topics: %w", err)
	}

	// 결과 확인
	for _, result := range results {
		if result.Error.Code() != kafka.ErrNoError && result.Error.Code() != kafka.ErrTopicAlreadyExists {
			config.Logger.Errorf("failed to create topic %s: %v", result.Topic, result.Error)
		} else {
			config.Logger.Infof("topic %s is ready", result.Topic)
		}
	}

	return nil
}
