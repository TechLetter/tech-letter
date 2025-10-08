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
	"tech-letter/kafka"
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

	// Kafka 설정 초기화
	kafkaConfig := kafka.NewConfig()

	// Kafka 토픽 생성
	if err := kafka.CreateTopicsIfNotExists(kafkaConfig); err != nil {
		config.Logger.Errorf("failed to create kafka topics: %v", err)
		// 토픽 생성 실패는 치명적이지 않으므로 계속 진행
	}

	// Kafka Producer 초기화 (이벤트 발행용)
	producer, err := kafka.NewProducer(kafkaConfig)
	if err != nil {
		config.Logger.Errorf("failed to create kafka producer: %v", err)
		os.Exit(1)
	}
	defer producer.Close()

	// 서비스 초기화
	eventService := eventServices.NewEventService(producer)
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
