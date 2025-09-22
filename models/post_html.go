package models

import (
	"time"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

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
