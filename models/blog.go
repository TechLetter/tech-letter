package models

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// Blog represents a tech blog source
// Collection: blogs
type Blog struct {
	ID        primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	CreatedAt time.Time          `bson:"created_at" json:"created_at"`
	UpdatedAt time.Time          `bson:"updated_at" json:"updated_at"`
	Name      string             `bson:"name" json:"name"`
	URL       string             `bson:"url" json:"url"`
	RSSURL    string             `bson:"rss_url" json:"rss_url"`
	BlogType  string             `bson:"blog_type" json:"blog_type"`
}
