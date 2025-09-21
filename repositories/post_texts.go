package repositories

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"

	"tech-letter/models"
)

type PostTextRepository struct {
	col *mongo.Collection
}

func NewPostTextRepository(db *mongo.Database) *PostTextRepository {
	return &PostTextRepository{col: db.Collection("post_texts")}
}

// FindByPostID returns the latest post_texts by post_id
func (r *PostTextRepository) FindByPostID(ctx context.Context, postID interface{}) (*models.PostText, error) {
	var doc models.PostText
	if err := r.col.FindOne(ctx, bson.M{"post_id": postID}).Decode(&doc); err != nil {
		return nil, err
	}
	return &doc, nil
}

// UpsertByPost updates or inserts by post_id
func (r *PostTextRepository) UpsertByPost(ctx context.Context, t *models.PostText) (*mongo.UpdateResult, error) {
	now := time.Now()
	if t.CreatedAt.IsZero() {
		t.CreatedAt = now
	}
	t.UpdatedAt = now

	filter := bson.M{"post_id": t.PostID}
	update := bson.M{
		"$setOnInsert": bson.M{"created_at": t.CreatedAt},
		"$set": bson.M{
			"updated_at":  t.UpdatedAt,
			"plain_text":  t.PlainText,
			"parsed_at":   t.ParsedAt,
			"word_count":  t.WordCount,
			"blog_name":   t.BlogName,
			"post_title":  t.PostTitle,
		},
	}
	opts := options.Update().SetUpsert(true)
	return r.col.UpdateOne(ctx, filter, update, opts)
}
