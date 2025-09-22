package models

import (
	"time"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

// PostAISummary stores AI summary result per post (normalized)
// Collection: post_ai_summaries
type PostAISummary struct {
	ID           primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	CreatedAt    time.Time          `bson:"created_at" json:"created_at"`
	UpdatedAt    time.Time          `bson:"updated_at" json:"updated_at"`
	PostID       primitive.ObjectID `bson:"post_id" json:"post_id"`
	AILogID      primitive.ObjectID `bson:"ai_log_id" json:"ai_log_id"`
	Categories   []string           `bson:"categories" json:"categories"`
	Tags         []string           `bson:"tags" json:"tags"`
	SummaryShort string             `bson:"summary_short" json:"summary_short"`
	SummaryLong  string             `bson:"summary_long" json:"summary_long"`
	ModelName    string             `bson:"model_name" json:"model_name"`
	GeneratedAt  time.Time          `bson:"generated_at" json:"generated_at"`
}
