package models

import (
	"time"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

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
