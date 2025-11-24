package models

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// Deprecated string statuses are removed in favor of boolean flags below.

// StatusFlags represents processing progress of a post
//
//	ai_summarized: AI 요약/분류가 저장됨
type StatusFlags struct {
	AISummarized    bool `bson:"ai_summarized" json:"ai_summarized"`
	ThumbnailParsed bool `bson:"thumbnail_parsed" json:"thumbnail_parsed"`
}

// Post represents a summarized post document
// Collection: posts
type Post struct {
	ID           primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	CreatedAt    time.Time          `bson:"created_at" json:"created_at"`
	UpdatedAt    time.Time          `bson:"updated_at" json:"updated_at"`
	Status       StatusFlags        `bson:"status" json:"status"`
	ViewCount    int64              `bson:"view_count" json:"view_count"`
	BlogID       primitive.ObjectID `bson:"blog_id" json:"blog_id"`
	BlogName     string             `bson:"blog_name" json:"blog_name"`
	Title        string             `bson:"title" json:"title"`
	Link         string             `bson:"link" json:"link"`
	PublishedAt  time.Time          `bson:"published_at" json:"published_at"`
	ThumbnailURL string             `bson:"thumbnail_url" json:"thumbnail_url"`
	AISummary    AISummary          `bson:"aisummary" json:"aisummary"`
}

// AISummary nested info in Post (denormalized snapshot)
// Stored under posts.aisummary
// Includes categories and tags arrays for indexing
type AISummary struct {
	Categories  []string  `bson:"categories" json:"categories"`
	Tags        []string  `bson:"tags" json:"tags"`
	Summary     string    `bson:"summary" json:"summary"`
	ModelName   string    `bson:"model_name" json:"model_name"`
	GeneratedAt time.Time `bson:"generated_at" json:"generated_at"`
}
