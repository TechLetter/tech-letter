package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"
	"time"

	"tech-letter/config"
	"tech-letter/db"
	eventServices "tech-letter/cmd/aggregate/services"
	"tech-letter/eventbus"
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
	aggregateService := NewAggregateService(eventService)

	config.Logger.Info("starting aggregate service (RSS feed collection)...")

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

	// 종료 신호 대기
	<-sigChan
	config.Logger.Info("received shutdown signal, shutting down aggregate service...")

	cancel()

	config.Logger.Info("aggregate service stopped")
}
