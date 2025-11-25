package eventbus

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"

	"tech-letter/config"
)

// KafkaEventBus는 confluent-kafka-go 라이브러리를 사용한 EventBus 구현체입니다.
type KafkaEventBus struct {
	Producer *kafka.Producer
	Brokers  string
}

// NewKafkaEventBus는 Kafka Producer를 초기화합니다.
func NewKafkaEventBus(brokers string) (*KafkaEventBus, error) {
	p, err := kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers": brokers,
		"acks":              "all",
		"retries":           5, // Producer는 일시적인 오류 발생 시 최대 5회 재시도합니다.
	})
	if err != nil {
		return nil, fmt.Errorf("kafka Producer 생성 실패: %w", err)
	}

	// Producer 이벤트를 처리하는 고루틴 (전달 보고서 등)
	go func() {
		for e := range p.Events() {
			switch ev := e.(type) {
			case *kafka.Message:
				if ev.TopicPartition.Error != nil {
					config.Logger.Errorf("메시지 전달 실패 %v: %v", ev.TopicPartition, ev.TopicPartition.Error)
				}
			case kafka.Error:
				config.Logger.Errorf("Kafka 오류: %v", ev)
			}
		}
	}()

	return &KafkaEventBus{
		Producer: p,
		Brokers:  brokers,
	}, nil
}

// Close는 Producer를 안전하게 종료합니다.
func (k *KafkaEventBus) Close() {
	if k.Producer != nil {
		// 5초 동안 남은 메시지를 모두 플러시합니다.
		if remaining := k.Producer.Flush(5000); remaining > 0 {
			config.Logger.Warnf("플러시 후에도 %d개의 메시지가 남아 있습니다.\n", remaining)
		}
		k.Producer.Close()
		config.Logger.Info("Kafka Producer 종료.")
	}
}

// Publish는 지정된 토픽에 이벤트를 발행합니다.
func (k *KafkaEventBus) Publish(ctx context.Context, topic string, event Event) error {
	data, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("이벤트 마샬링 실패: %w", err)
	}

	deliveryChan := make(chan kafka.Event, 1)
	defer close(deliveryChan)

	// 메시지 생성 및 전송
	err = k.Producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
		Value:          data,
		Key:            []byte(event.ID),
	}, deliveryChan)
	if err != nil {
		return fmt.Errorf("메시지 발행 실패: %w", err)
	}

	// 전달 성공/실패 대기
	select {
	case ev := <-deliveryChan:
		m := ev.(*kafka.Message)
		if m.TopicPartition.Error != nil {
			return fmt.Errorf("메시지 전달 실패: %w", m.TopicPartition.Error)
		}
	case <-ctx.Done():
		return ctx.Err()
	}

	return nil
}

// Subscribe는 기본 토픽을 구독하고 메인 비즈니스 핸들러를 실행합니다.
func (k *KafkaEventBus) Subscribe(ctx context.Context, groupID string, topic Topic, handler EventHandler) error {
	c, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers":             k.Brokers,
		"group.id":                      groupID, // 메인 컨슈머 그룹 ID
		"auto.offset.reset":             "earliest",
		"enable.auto.commit":            false, // 재시도 로직을 위해 수동 커밋 사용
		"partition.assignment.strategy": "range",
	})
	if err != nil {
		return fmt.Errorf("kafka Consumer 생성 실패: %w", err)
	}
	defer c.Close()

	topicsToSubscribe := []string{topic.Base()}
	if err := c.SubscribeTopics(topicsToSubscribe, nil); err != nil {
		return fmt.Errorf("토픽 구독 실패 %v: %w", topicsToSubscribe, err)
	}

	config.Logger.Infof("메인 컨슈머 (%s) 시작됨. 구독 토픽: %s", groupID, strings.Join(topicsToSubscribe, ", "))

	for {
		select {
		case <-ctx.Done():
			config.Logger.Info("메인 컨슈머 종료 중.")
			return ctx.Err()
		default:
			msg, err := c.ReadMessage(100 * time.Millisecond)
			if err != nil {
				if kerr, ok := err.(kafka.Error); ok && kerr.Code() == kafka.ErrTimedOut {
					continue // 타임아웃은 정상적인 상황입니다.
				}
				continue
			}

			var evt Event
			if err := json.Unmarshal(msg.Value, &evt); err != nil {
				config.Logger.Errorf("토픽 %s의 이벤트 페이로드 오류: %v. 메시지를 건너뛰고 커밋합니다.\n", *msg.TopicPartition.Topic, err)
				c.CommitMessage(msg)
				continue
			}

			// 이벤트의 최대 재시도 기본값 보정 (설정되지 않았거나 범위를 초과한 경우)
			if evt.MaxRetry <= 0 || evt.MaxRetry > len(RetryDelays) {
				evt.MaxRetry = len(RetryDelays)
			}

			// 1. 핸들러 실행 (비즈니스 로직)
			if evt.Retry > 0 {
				config.Logger.Infof("이벤트 %s 처리 시작 (재시도 %d/%d) - 토픽: %s", evt.ID, evt.Retry, evt.MaxRetry, *msg.TopicPartition.Topic)
			} else {
				config.Logger.Debugf("이벤트 %s 처리 시작 - 토픽: %s", evt.ID, *msg.TopicPartition.Topic)
			}
			err = handler(ctx, evt)

			if err != nil {
				// 2. 핸들러 실패: 재시도 또는 DLQ 결정
				evt.LastError = err.Error()
				nextRetryCount := evt.Retry + 1
				nextRetryTopic, getTopicErr := topic.GetRetryTopic(nextRetryCount)

				if getTopicErr == ErrMaxRetryExceeded {
					// 2-1. 최대 재시도 횟수 초과 -> DLQ 발행
					config.Logger.Errorf("이벤트 %s의 최대 재시도 횟수 초과. DLQ %s로 전송. 최종 오류: %s\n", evt.ID, topic.DLQ(), err.Error())
					publishErr := k.Publish(ctx, topic.DLQ(), evt)
					if publishErr != nil {
						config.Logger.Errorf("DLQ %s 발행 실패: %v. 오프셋 커밋 안함.\n", topic.DLQ(), publishErr)
						continue // 발행 실패 시 메시지 재처리 시도
					}
				} else if getTopicErr != nil {
					config.Logger.Errorf("재시도 토픽 결정 중 예상치 못한 오류 발생: %v. 오프셋 커밋 안함.\n", getTopicErr)
					continue
				} else {
					// 2-2. 재시도 예약 (지연 토픽으로 발행)
					evt.Retry = nextRetryCount
					config.Logger.Warnf("이벤트 %s 처리 실패. 재시도 %d/%d를 토픽 %s에 예약.",
						evt.ID, evt.Retry, evt.MaxRetry, nextRetryTopic)
					publishErr := k.Publish(ctx, nextRetryTopic, evt)
					if publishErr != nil {
						config.Logger.Errorf("재시도 이벤트 토픽 %s 발행 실패: %v. 오프셋 커밋 안함.", nextRetryTopic, publishErr)
						continue
					}
				}
			}

			// 3. 성공 또는 재시도/DLQ 발행 성공 시 오프셋 커밋
			if _, err := c.CommitMessage(msg); err != nil {
				config.Logger.Errorf("오프셋 커밋 오류: %v", err)
			}
		}
	}
}

// StartRetryReinjector는 모든 재시도 토픽을 구독하고 메시지를 기본 토픽으로 재발행(re-publish)합니다.
func (k *KafkaEventBus) StartRetryReinjector(ctx context.Context, groupID string, topic Topic) error {
	c, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers":             k.Brokers,
		"group.id":                      groupID, // 전용 재주입 그룹 ID
		"auto.offset.reset":             "earliest",
		"enable.auto.commit":            false,
		"partition.assignment.strategy": "range",
	})
	if err != nil {
		return fmt.Errorf("kafka 재시도 재주입기 생성 실패: %w", err)
	}
	defer c.Close()

	retryTopics := topic.GetRetryTopics()
	if err := c.SubscribeTopics(retryTopics, nil); err != nil {
		return fmt.Errorf("재시도 토픽 구독 실패 %v: %w", retryTopics, err)
	}

	config.Logger.Infof("재시도 재주입 컨슈머 (%s) 시작됨. 구독 토픽: %s", groupID, strings.Join(retryTopics, ", "))

	for {
		select {
		case <-ctx.Done():
			config.Logger.Info("재시도 재주입 컨슈머 종료 중.")
			return ctx.Err()
		default:
			msg, err := c.ReadMessage(100 * time.Millisecond)
			if err != nil {
				if kerr, ok := err.(kafka.Error); ok {
					if kerr.Code() == kafka.ErrTimedOut {
						continue
					}
					if kerr.IsFatal() {
						return fmt.Errorf("재시도 재주입 컨슈머 치명적 오류: %w", err)
					}
				}
				config.Logger.Errorf("재시도 재주입 컨슈머 ReadMessage 오류: %v", err)
				time.Sleep(500 * time.Millisecond)
				continue
			}

			// 토픽명에서 재시도 지연 시간 추출 및 준비시간 확인
			topicName := *msg.TopicPartition.Topic
			delayDur, ok := ParseRetryDelayFromTopicName(topicName)
			if !ok {
				config.Logger.Errorf("재시도 토픽 이름 파싱 실패: %s. 메시지를 건너뛰고 커밋합니다.", topicName)
				c.CommitMessage(msg)
				continue
			}

			readyAt := msg.Timestamp.Add(delayDur)
			now := time.Now()
			if now.Before(readyAt) {
				remaining := readyAt.Sub(now)
				// 전체 컨슈머 스레드 블로킹을 피하기 위해 아주 짧게만 대기
				sleepDur := remaining
				if sleepDur > 500*time.Millisecond {
					sleepDur = 500 * time.Millisecond
				} else if sleepDur < 50*time.Millisecond {
					sleepDur = 50 * time.Millisecond
				}
				time.Sleep(sleepDur)
				// 오프셋 커밋 없이 재시도 (메시지는 다시 전달됨)
				continue
			}

			var evt Event
			if err := json.Unmarshal(msg.Value, &evt); err != nil {
				config.Logger.Errorf("재시도 토픽 %s의 이벤트 페이로드 오류: %v. 메시지를 건너뛰고 커밋합니다.\n", *msg.TopicPartition.Topic, err)
				c.CommitMessage(msg)
				continue
			}

			// 1. 메시지를 메인 토픽으로 재주입
			config.Logger.Infof("이벤트 %s를 %s에서 %s로 재주입. (재시도: %d)",
				evt.ID, *msg.TopicPartition.Topic, topic.Base(), evt.Retry)

			if err := k.Publish(ctx, topic.Base(), evt); err != nil {
				config.Logger.Errorf("이벤트 %s 재주입 실패: %v. 오프셋 커밋 안함.\n", evt.ID, err)
				continue // 재발행 실패 시 메시지 재처리 시도
			}

			// 2. 재발행 성공했으므로, 지연 토픽의 오프셋 커밋
			if _, err := c.CommitMessage(msg); err != nil {
				config.Logger.Errorf("재주입 후 커밋 오류: %v\n", err)
			}
		}
	}
}
