package eventbus

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

// EnsureTopics는 기본 토픽, 모든 지연 토픽, DLQ 토픽을 생성합니다.
// 이미 존재하는 토픽에 대해서는 성공으로 간주합니다.
func EnsureTopics(brokers string, topic Topic, basePartitions int) error {
	admin, err := kafka.NewAdminClient(&kafka.ConfigMap{
		"bootstrap.servers": brokers,
	})
	if err != nil {
		return fmt.Errorf("AdminClient 생성 실패: %w", err)
	}
	defer admin.Close()

	// 생성할 토픽 사양 구성
	specs := make([]kafka.TopicSpecification, 0, 2+len(RetryDelays))

	// 기본 토픽
	specs = append(specs, kafka.TopicSpecification{
		Topic:             topic.Base(),
		NumPartitions:     basePartitions,
		ReplicationFactor: 1,
	})

	// DLQ 토픽 (1 파티션 권장)
	specs = append(specs, kafka.TopicSpecification{
		Topic:             topic.DLQ(),
		NumPartitions:     1,
		ReplicationFactor: 1,
	})

	// 재시도 토픽들 (기본 토픽과 동일한 파티션 수 권장)
	for _, retryTopic := range topic.GetRetryTopics() {
		specs = append(specs, kafka.TopicSpecification{
			Topic:             retryTopic,
			NumPartitions:     basePartitions,
			ReplicationFactor: 1,
		})
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	results, err := admin.CreateTopics(ctx, specs)
	if err != nil {
		return fmt.Errorf("토픽 생성 요청 실패: %w", err)
	}

	for _, r := range results {
		code := r.Error.Code()
		if code != kafka.ErrNoError && code != kafka.ErrTopicAlreadyExists {
			return fmt.Errorf("토픽 %s 생성 실패: %v", r.Topic, r.Error)
		}
	}

	return nil
}

// ParseRetryFromTopicName는 토픽 이름의 ".retry." 접두사 이후의 문자열을 time.Duration으로 파싱합니다.
// 예: "tech-letter.post.events.retry.1m0s" -> 1m0s
func ParseRetryFromTopicName(name string) (time.Duration, bool) {
	idx := strings.LastIndex(name, ".retry.")
	if idx == -1 || idx+7 >= len(name) {
		return 0, false
	}
	durStr := name[idx+7:]
	d, err := time.ParseDuration(durStr)
	if err != nil {
		return 0, false
	}
	return d, true
}
