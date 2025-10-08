package main

import (
	"context"
	"os"
	"os/signal"
	"sync"
	"syscall"

	eventHandlers "tech-letter/cmd/processor/handlers"
	eventServices "tech-letter/cmd/processor/services"
	"tech-letter/config"
	"tech-letter/db"
	"tech-letter/events"
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

	// Kafka Producer 초기화
	producer, err := kafka.NewProducer(kafkaConfig)
	if err != nil {
		config.Logger.Errorf("failed to create kafka producer: %v", err)
		os.Exit(1)
	}
	defer producer.Close()

	// Kafka Consumer 초기화
	consumer, err := kafka.NewConsumer(kafkaConfig)
	if err != nil {
		config.Logger.Errorf("failed to create kafka consumer: %v", err)
		os.Exit(1)
	}
	defer consumer.Close()

	// 서비스 초기화
	eventService := eventServices.NewEventService(producer)
	handlers := eventHandlers.NewEventHandlers(eventService)

	// 이벤트 핸들러 등록
	consumer.RegisterHandler(events.PostCreated, handlers.HandlePostCreated)
	consumer.RegisterHandler(events.PostHTMLFetched, handlers.HandlePostHTMLFetched)
	consumer.RegisterHandler(events.PostTextParsed, handlers.HandlePostTextParsed)
	consumer.RegisterHandler(events.PostSummarized, handlers.HandlePostSummarized)

	// 토픽 구독
	if err := consumer.Subscribe([]string{kafka.TopicPostEvents}); err != nil {
		config.Logger.Errorf("failed to subscribe to topics: %v", err)
		os.Exit(1)
	}

	config.Logger.Info("starting processor service...")

	// Graceful shutdown 설정
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	var wg sync.WaitGroup

	// Kafka Consumer 시작
	wg.Add(1)
	go func() {
		defer wg.Done()
		if err := consumer.Start(ctx); err != nil && err != context.Canceled {
			config.Logger.Errorf("kafka consumer error: %v", err)
		}
	}()

	// 종료 신호 대기
	<-sigChan
	config.Logger.Info("received shutdown signal, shutting down processor service...")

	cancel()
	wg.Wait()

	config.Logger.Info("processor service stopped")
}
