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

// IsExistByPostID checks if a post_text exists for a given post_id
func (r *PostTextRepository) IsExistByPostID(ctx context.Context, postID interface{}) (bool, error) {
	err := r.col.FindOne(ctx, bson.M{"post_id": postID}).Err()
	if err == mongo.ErrNoDocuments {
		return false, nil
	}
	return err == nil, err
}

// Insert creates a new post_text document
func (r *PostTextRepository) Insert(ctx context.Context, t *models.PostText) (*mongo.InsertOneResult, error) {
	now := time.Now()
	if t.CreatedAt.IsZero() {
		t.CreatedAt = now
	}
	t.UpdatedAt = now
	return r.col.InsertOne(ctx, t)
}

// UpdateByPostID updates fields of post_text by post_id
func (r *PostTextRepository) UpdateByPostID(ctx context.Context, t *models.PostText) (*mongo.UpdateResult, error) {
	t.UpdatedAt = time.Now()
	filter := bson.M{"post_id": t.PostID}
	update := bson.M{"$set": bson.M{
		"updated_at":  t.UpdatedAt,
		"plain_text":  t.PlainText,
		"parsed_at":   t.ParsedAt,
		"word_count":  t.WordCount,
		"blog_name":   t.BlogName,
		"post_title":  t.PostTitle,
	}}
	return r.col.UpdateOne(ctx, filter, update, options.Update())
}
