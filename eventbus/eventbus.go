package eventbus

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

// RetryDelays는 재시도 횟수(1-based)별로 사용할 고정된 지연 시간 목록입니다.
var RetryDelays = []time.Duration{
	10 * time.Second, // 1차 재시도 (시도 1)
	30 * time.Second, // 2차 재시도 (시도 2)
	1 * time.Minute,  // 3차 재시도 (시도 3)
	5 * time.Minute,  // 4차 재시도 (시도 4)
	10 * time.Minute, // 5차 재시도 (시도 5)
}

// Topic은 토픽의 기본 이름, 재시도 토픽, DLQ 토픽 이름을 관리합니다.
type Topic struct {
	base string
}

func NewTopic(base string) Topic {
	return Topic{base: base}
}

func (t Topic) Base() string {
	return t.base
}

// DLQ는 DLQ 토픽 이름을 반환합니다 (예: my_topic.dlq).
func (t Topic) DLQ() string {
	return t.base + ".dlq"
}

// GetRetryTopics는 모든 재시도 토픽의 이름을 반환합니다.
func (t Topic) GetRetryTopics() []string {
	topics := make([]string, len(RetryDelays))
	for i, delay := range RetryDelays {
		// 토픽 이름 형식: base.retry.10s
		topics[i] = fmt.Sprintf("%s.retry.%s", t.base, delay.String())
	}
	return topics
}

// GetRetryTopic은 다음 재시도 횟수(1-based)에 해당하는 재시도 토픽 이름을 반환합니다.
func (t Topic) GetRetryTopic(retryCount int) (string, error) {
	// retryCount는 1부터 시작하며, 인덱스 (retryCount-1)를 사용합니다.
	if retryCount <= 0 || retryCount > len(RetryDelays) {
		return "", ErrMaxRetryExceeded
	}
	delay := RetryDelays[retryCount-1]
	return fmt.Sprintf("%s.retry.%s", t.base, delay.String()), nil
}

// Event는 Kafka 메시지의 페이로드로 사용되는 구조체입니다.
type Event struct {
	ID        string          `json:"id"`
	Payload   json.RawMessage `json:"payload"`
	Retry     int             `json:"retry"` // 현재 재시도 횟수 (0부터 시작)
	MaxRetry  int             `json:"max_retry"`
	LastError string          `json:"last_error,omitempty"`
}

// EventHandler는 이벤트 처리 함수의 시그니처입니다.
type EventHandler func(ctx context.Context, event Event) error

// EventBus 인터페이스는 이벤트 발행 및 구독의 추상화를 정의합니다.
type EventBus interface {
	Publish(ctx context.Context, topic string, event Event) error
	// Subscribe는 기본 토픽을 구독하여 메인 로직을 실행합니다.
	Subscribe(ctx context.Context, groupID string, topic Topic, handler EventHandler) error
	// StartRetryReinjector는 모든 재시도 토픽을 구독하고 기본 토픽으로 이벤트를 재발행합니다.
	StartRetryReinjector(ctx context.Context, groupID string, topic Topic) error
	Close()
}

// ErrMaxRetryExceeded는 최대 재시도 횟수를 초과했을 때 반환되는 오류입니다.
var ErrMaxRetryExceeded = errors.New("최대 재시도 횟수 초과")

// ErrRetryScheduleFailed는 재시도 또는 DLQ 발행에 실패했을 때 반환되는 오류입니다.
var ErrRetryScheduleFailed = errors.New("재시도 또는 DLQ 발행 실패")
