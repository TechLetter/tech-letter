package main

import (
	"context"
	"encoding/json"
	"os"
	"os/signal"
	"sync"
	"syscall"

	eventHandlers "tech-letter/cmd/processor/handlers"
	eventServices "tech-letter/cmd/processor/services"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/eventbus"
	"tech-letter/events"
)

func main() {
	config.InitApp()
	config.InitLogger()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// MongoDB 초기화
	if err := db.Init(ctx); err != nil {
		config.Logger.Errorf("failed to initialize MongoDB: %v", err)
		os.Exit(1)
	}

	// EventBus 초기화 및 토픽 보장
	brokers := eventbus.GetBrokers()
	if err := eventbus.EnsureTopics(brokers, eventbus.TopicPostEvents, 3); err != nil {
		config.Logger.Errorf("failed to ensure eventbus topics: %v", err)
	}

	bus, err := eventbus.NewKafkaEventBus(brokers)
	if err != nil {
		config.Logger.Errorf("failed to create event bus: %v", err)
		os.Exit(1)
	}
	defer bus.Close()

	// 서비스 초기화
	eventService := eventServices.NewEventService(bus)
	handlers := eventHandlers.NewEventHandlers(eventService)

	// 재주입기 시작 (지연 토픽 -> 기본 토픽)
	groupID := eventbus.GetGroupID()

	// 메인 구독 러너
	subscribeRunner := func() error {
		return bus.Subscribe(ctx, groupID, eventbus.TopicPostEvents, func(ctx context.Context, ev eventbus.Event) error {
			// 이벤트 타입만 먼저 파싱 (BaseEvent.Type는 top-level에 있음)
			var peek struct {
				Type string `json:"type"`
			}
			if err := json.Unmarshal(ev.Payload, &peek); err != nil {
				return err
			}
			switch events.EventType(peek.Type) {
			case events.PostCreated:
				v, err := eventbus.DecodeJSON[events.PostCreatedEvent](ev)
				if err != nil {
					return err
				}
				return handlers.HandlePostCreated(ctx, &v)
			default:
				// 알 수 없는 타입 또는 다른 서비스용 이벤트는 무시 (커밋)
				return nil
			}
		})
	}

	config.Logger.Info("starting processor service with eventbus...")

	// Graceful shutdown 설정
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	var wg sync.WaitGroup

	// 메인 구독 시작
	wg.Add(1)
	go func() {
		defer wg.Done()
		if err := subscribeRunner(); err != nil && err != context.Canceled {
			config.Logger.Errorf("eventbus subscribe error: %v", err)
		}
	}()

	// 재시도 재주입기 시작
	wg.Add(1)
	go func() {
		defer wg.Done()
		if err := bus.StartRetryReinjector(ctx, groupID+"-reinject", eventbus.TopicPostEvents); err != nil && err != context.Canceled {
			config.Logger.Errorf("eventbus retry reinjector error: %v", err)
		}
	}()

	// 종료 신호 대기
	<-sigChan
	config.Logger.Info("received shutdown signal, shutting down processor service...")

	cancel()
	wg.Wait()

	config.Logger.Info("processor service stopped")
}
