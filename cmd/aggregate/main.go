package main

import (
	"context"
	"encoding/json"
	"os"
	"os/signal"
	"syscall"
	"time"

	aggHandlers "tech-letter/cmd/aggregate/handlers"
	eventServices "tech-letter/cmd/aggregate/services"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/eventbus"
	"tech-letter/events"
)

func main() {
	config.InitApp()
	cfg := config.GetConfig()
	config.InitLogger(cfg.Aggregate.Logging)

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
	aggregateService := NewAggregateService(eventService)
	recoveryService := NewRecoveryService(eventService)
	handlers := aggHandlers.NewEventHandlers()

	config.Logger.Info("starting aggregate service (RSS feed collection and DB writer)...")

	// Graceful shutdown 설정
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// RSS 피드 수집 고루틴 시작
	go func() {
		ticker := time.NewTicker(30 * time.Minute) // 30분마다 실행
		defer ticker.Stop()

		// 시작 시 즉시 한 번 실행
		if err := aggregateService.RunFeedCollection(ctx); err != nil {
			config.Logger.Errorf("initial feed collection failed: %v", err)
		}

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := aggregateService.RunFeedCollection(ctx); err != nil {
					config.Logger.Errorf("feed collection failed: %v", err)
				}
			}
		}
	}()

	// 요약이 완료되지 않은 포스트에 대한 자동 복구 고루틴 시작
	go func() {
		ticker := time.NewTicker(6 * time.Hour)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := recoveryService.RunSummaryRecovery(ctx, 100); err != nil {
					config.Logger.Errorf("unsummarized posts recovery failed: %v", err)
				}
			}
		}
	}()

	// 썸네일 파싱이 완료되지 않은 포스트에 대한 자동 복구 고루틴 시작
	go func() {
		ticker := time.NewTicker(6 * time.Hour)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := recoveryService.RunThumbnailRecovery(ctx, 100); err != nil {
					config.Logger.Errorf("thumbnail recovery failed: %v", err)
				}
			}
		}
	}()

	// PostSummarized 이벤트를 소비하여 DB에 결과 반영
	go func() {
		groupID := eventbus.GetGroupID() + "-aggregate-writer"
		if err := bus.Subscribe(ctx, groupID, eventbus.TopicPostEvents, func(ctx context.Context, ev eventbus.Event) error {
			var peek struct {
				Type string `json:"type"`
			}
			if err := json.Unmarshal(ev.Payload, &peek); err != nil {
				return err
			}
			switch events.EventType(peek.Type) {
			case events.PostSummarized:
				v, err := eventbus.DecodeJSON[events.PostSummarizedEvent](ev)
				if err != nil {
					return err
				}
				return handlers.HandlePostSummarized(ctx, &v)
			case events.PostThumbnailParsed:
				v, err := eventbus.DecodeJSON[events.PostThumbnailParsedEvent](ev)
				if err != nil {
					return err
				}
				return handlers.HandlePostThumbnailParsed(ctx, &v)
			default:
				// Aggregate는 요약 결과와 썸네일 결과만 관심 있음. 나머지 이벤트는 무시.
				return nil
			}
		}); err != nil && err != context.Canceled {
			config.Logger.Errorf("aggregate eventbus subscribe error: %v", err)
		}
	}()

	// 종료 신호 대기
	<-sigChan
	config.Logger.Info("received shutdown signal, shutting down aggregate service...")

	cancel()

	config.Logger.Info("aggregate service stopped")
}
