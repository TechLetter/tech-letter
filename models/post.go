package models

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// Deprecated string statuses are removed in favor of boolean flags below.

// StatusFlags represents processing progress of a post
//   html_fetched: HTML이 성공적으로 수집됨
//   text_parsed: 본문 텍스트가 파싱되어 저장됨
//   ai_summarized: AI 요약/분류가 저장됨
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
	ViewCount          int64              `bson:"view_count" json:"view_count"`
	BlogID             primitive.ObjectID `bson:"blog_id" json:"blog_id"`
	BlogName           string             `bson:"blog_name" json:"blog_name"`
	Title              string             `bson:"title" json:"title"`
	Link               string             `bson:"link" json:"link"`
	PublishedAt        time.Time          `bson:"published_at" json:"published_at"`
	SummaryShort       string             `bson:"summary_short" json:"summary_short"`
	ReadingTimeMinutes int                `bson:"reading_time_minutes" json:"reading_time_minutes"`
	AIGeneratedInfo    AIGeneratedInfo    `bson:"ai_generated_info" json:"ai_generated_info"`
}

// AIGeneratedInfo nested info in Post
// Stored under posts.ai_generated_info
// Includes categories and tags arrays for indexing
type AIGeneratedInfo struct {
	Categories      []string  `bson:"categories" json:"categories"`
	Tags            []string  `bson:"tags" json:"tags"`
	SummaryShort    string    `bson:"summary_short" json:"summary_short"`
	SummaryLong     string    `bson:"summary_long" json:"summary_long"`
	ModelName       string    `bson:"model_name" json:"model_name"`
	ConfidenceScore float64   `bson:"confidence_score" json:"confidence_score"`
	GeneratedAt     time.Time `bson:"generated_at" json:"generated_at"`
}

// PostHTML stores raw html
// Collection: post_htmls
type PostHTML struct {
	ID              primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	CreatedAt       time.Time          `bson:"created_at" json:"created_at"`
	UpdatedAt       time.Time          `bson:"updated_at" json:"updated_at"`
	PostID          primitive.ObjectID `bson:"post_id" json:"post_id"`
	RawHTML         string             `bson:"raw_html" json:"raw_html"`
	FetchedAt       time.Time          `bson:"fetched_at" json:"fetched_at"`
	FetchDurationMs int64              `bson:"fetch_duration_ms" json:"fetch_duration_ms"`
	HTMLSizeBytes   int64              `bson:"html_size_bytes" json:"html_size_bytes"`
	BlogName        string             `bson:"blog_name" json:"blog_name"`
	PostTitle       string             `bson:"post_title" json:"post_title"`
}

// PostText stores parsed plain text
// Collection: post_texts
type PostText struct {
	ID        primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	CreatedAt time.Time          `bson:"created_at" json:"created_at"`
	UpdatedAt time.Time          `bson:"updated_at" json:"updated_at"`
	PostID    primitive.ObjectID `bson:"post_id" json:"post_id"`
	PlainText string             `bson:"plain_text" json:"plain_text"`
	ParsedAt  time.Time          `bson:"parsed_at" json:"parsed_at"`
	WordCount int                `bson:"word_count" json:"word_count"`
	BlogName  string             `bson:"blog_name" json:"blog_name"`
	PostTitle string             `bson:"post_title" json:"post_title"`
}

// AILog stores LLM usage logs
// Collection: ai_logs
type AILog struct {
	ID               primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	PostID           primitive.ObjectID `bson:"post_id" json:"post_id"`
	Model            string             `bson:"model" json:"model"`
	PromptTokens     int                `bson:"prompt_tokens" json:"prompt_tokens"`
	CompletionTokens int                `bson:"completion_tokens" json:"completion_tokens"`
	TotalTokens      int                `bson:"total_tokens" json:"total_tokens"`
	DurationMs       int64              `bson:"duration_ms" json:"duration_ms"`
	Success          bool               `bson:"success" json:"success"`
	ResponseExcerpt  string             `bson:"response_excerpt" json:"response_excerpt"`
	ErrorMessage     *string            `bson:"error_message,omitempty" json:"error_message,omitempty"`
	RequestedAt      time.Time          `bson:"requested_at" json:"requested_at"`
	CompletedAt      time.Time          `bson:"completed_at" json:"completed_at"`
}
