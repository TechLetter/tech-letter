package main

import (
	"context"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"tech-letter/cmd/internal/eventbus"
	"tech-letter/cmd/internal/logger"
)

func main() {
	// Retry worker 로그 레벨은 환경변수 LOG_LEVEL 로 제어한다.
	logger.InitFromEnv("LOG_LEVEL")

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	brokers := eventbus.GetBrokers()
	for _, t := range eventbus.AllTopics {
		if err := eventbus.EnsureTopics(brokers, t, 3); err != nil {
			logger.Log.Errorf("failed to ensure eventbus topics for %s: %v", t.Base(), err)
		}
	}

	bus, err := eventbus.NewKafkaEventBus(brokers)
	if err != nil {
		logger.Log.Errorf("failed to create event bus: %v", err)
		os.Exit(1)
	}
	defer bus.Close()

	groupID := eventbus.GetGroupID() + "-retry-worker"

	logger.Log.Info("starting retry worker service with eventbus...")

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	for _, t := range eventbus.AllTopics {
		topic := t
		go func() {
			topicGroupID := groupID + "-" + strings.ReplaceAll(topic.Base(), ".", "-")
			if err := bus.StartRetryReinjector(ctx, topicGroupID, topic); err != nil && err != context.Canceled {
				logger.Log.Errorf("eventbus retry reinjector error for %s: %v", topic.Base(), err)
			}
		}()
	}

	<-sigChan
	logger.Log.Info("received shutdown signal, shutting down retry worker service...")

	cancel()

	logger.Log.Info("retry worker service stopped")
}
