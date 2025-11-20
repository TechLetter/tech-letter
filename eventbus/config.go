package eventbus

import (
	"os"
)

// GetBrokers returns Kafka bootstrap servers from env KAFKA_BOOTSTRAP_SERVERS
func GetBrokers() string {
	v := os.Getenv("KAFKA_BOOTSTRAP_SERVERS")
	if v == "" {
		panic("KAFKA_BOOTSTRAP_SERVERS environment variable is required")
	}
	return v
}

// GetGroupID returns consumer group id from env KAFKA_GROUP_ID
func GetGroupID() string {
	v := os.Getenv("KAFKA_GROUP_ID")
	if v == "" {
		panic("KAFKA_GROUP_ID environment variable is required")
	}
	return v
}
