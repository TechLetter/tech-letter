package models

import (
    "time"
    "go.mongodb.org/mongo-driver/bson/primitive"
)

// AILog stores LLM usage logs (system monitoring purpose)
// Collection: ai_logs
type AILog struct {
	ID             primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	ModelName      string             `bson:"model_name" json:"model_name"`
	ModelVersion   string             `bson:"model_version" json:"model_version"`
	InputTokens    int64              `bson:"input_tokens" json:"input_tokens"`
	OutputTokens   int64              `bson:"output_tokens" json:"output_tokens"`
	TotalTokens    int64              `bson:"total_tokens" json:"total_tokens"`
	DurationMs     int64              `bson:"duration_ms" json:"duration_ms"`
	ErrorMessage   *string            `bson:"error_message,omitempty" json:"error_message,omitempty"`
	InputPrompt    string             `bson:"input_prompt" json:"input_prompt"`
	OutputResponse string             `bson:"output_response" json:"output_response"`
	RequestedAt    time.Time          `bson:"requested_at" json:"requested_at"`
	CompletedAt    time.Time          `bson:"completed_at" json:"completed_at"`
}
