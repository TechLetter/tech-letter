package eventbus

import (
	"context"
	"encoding/json"
	"fmt"
	"time"
)

// NewJSONEvent 생성: payload를 JSON으로 인코딩하여 Event를 구성합니다.
// id가 빈 문자열이면 고해상도 타임스탬프 기반의 ID를 생성합니다.
func NewJSONEvent(id string, payload any, maxRetry int) (Event, error) {
	if maxRetry <= 0 || maxRetry > len(RetryDelays) {
		maxRetry = len(RetryDelays)
	}
	if id == "" {
		id = fmt.Sprintf("%d", time.Now().UnixNano())
	}
	b, err := json.Marshal(payload)
	if err != nil {
		return Event{}, fmt.Errorf("payload marshal 실패: %w", err)
	}
	return Event{
		ID:       id,
		Payload:  b,
		Retry:    0,
		MaxRetry: maxRetry,
	}, nil
}

// DecodeJSON은 Event.Payload를 제네릭 타입으로 언마샬합니다.
func DecodeJSON[T any](evt Event) (T, error) {
	var out T
	if err := json.Unmarshal(evt.Payload, &out); err != nil {
		var zero T
		return zero, fmt.Errorf("payload unmarshal 실패: %w", err)
	}
	return out, nil
}

// SubscribeJSON은 JSON 페이로드를 자동으로 디코딩해주는 Subscribe 헬퍼입니다.
// handler는 디코딩된 payload와 원본 메타(Event)를 함께 받습니다.
func SubscribeJSON[T any](ctx context.Context, bus EventBus, groupID string, topic Topic, handler func(ctx context.Context, payload T, meta Event) error) error {
	return bus.Subscribe(ctx, groupID, topic, func(ctx context.Context, evt Event) error {
		v, err := DecodeJSON[T](evt)
		if err != nil {
			return err
		}
		return handler(ctx, v, evt)
	})
}
