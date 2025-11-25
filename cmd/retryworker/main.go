package main

import (
	"context"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"tech-letter/config"
	"tech-letter/eventbus"
)

func main() {
	config.InitApp()
	cfg := config.GetConfig()
	config.InitLogger(cfg.Processor.Logging)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	brokers := eventbus.GetBrokers()
	for _, t := range eventbus.AllTopics {
		if err := eventbus.EnsureTopics(brokers, t, 3); err != nil {
			config.Logger.Errorf("failed to ensure eventbus topics for %s: %v", t.Base(), err)
		}
	}

	bus, err := eventbus.NewKafkaEventBus(brokers)
	if err != nil {
		config.Logger.Errorf("failed to create event bus: %v", err)
		os.Exit(1)
	}
	defer bus.Close()

	groupID := eventbus.GetGroupID() + "-retry-worker"

	config.Logger.Info("starting retry worker service with eventbus...")

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	for _, t := range eventbus.AllTopics {
		topic := t
		go func() {
			topicGroupID := groupID + "-" + strings.ReplaceAll(topic.Base(), ".", "-")
			if err := bus.StartRetryReinjector(ctx, topicGroupID, topic); err != nil && err != context.Canceled {
				config.Logger.Errorf("eventbus retry reinjector error for %s: %v", topic.Base(), err)
			}
		}()
	}

	<-sigChan
	config.Logger.Info("received shutdown signal, shutting down retry worker service...")

	cancel()

	config.Logger.Info("retry worker service stopped")
}
