package models

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// Deprecated string statuses are removed in favor of boolean flags below.

// StatusFlags represents processing progress of a post
//
//	html_fetched: HTML이 성공적으로 수집됨
//	text_parsed: 본문 텍스트가 파싱되어 저장됨
//	ai_summarized: AI 요약/분류가 저장됨
type StatusFlags struct {
	HTMLFetched  bool `bson:"html_fetched" json:"html_fetched"`
	TextParsed   bool `bson:"text_parsed" json:"text_parsed"`
	AISummarized bool `bson:"ai_summarized" json:"ai_summarized"`
}

// Post represents a summarized post document
// Collection: posts
type Post struct {
	ID                 primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	CreatedAt          time.Time          `bson:"created_at" json:"created_at"`
	UpdatedAt          time.Time          `bson:"updated_at" json:"updated_at"`
	Status             StatusFlags        `bson:"status" json:"status"`
	ViewCount          int64              `bson:"view_count" json:"view_count"` // todo: implement
	BlogID             primitive.ObjectID `bson:"blog_id" json:"blog_id"`
	BlogName           string             `bson:"blog_name" json:"blog_name"`
	Title              string             `bson:"title" json:"title"`
	Link               string             `bson:"link" json:"link"`
	PublishedAt        time.Time          `bson:"published_at" json:"published_at"`
	ThumbnailURL       string             `bson:"thumbnail_url" json:"thumbnail_url"`
	ReadingTimeMinutes int                `bson:"reading_time_minutes" json:"reading_time_minutes"` // todo: implement
	AISummary          AISummary          `bson:"aisummary" json:"aisummary"`
}

// AISummary nested info in Post (denormalized snapshot)
// Stored under posts.aisummary
// Includes categories and tags arrays for indexing
type AISummary struct {
	Categories   []string  `bson:"categories" json:"categories"`
	Tags         []string  `bson:"tags" json:"tags"`
	SummaryShort string    `bson:"summary_short" json:"summary_short"`
	SummaryLong  string    `bson:"summary_long" json:"summary_long"`
	ModelName    string    `bson:"model_name" json:"model_name"`
	GeneratedAt  time.Time `bson:"generated_at" json:"generated_at"`
}
