package repositories

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"

	"tech-letter/models"
)

type PostHTMLRepository struct {
	col *mongo.Collection
}

// FindByPostID returns the latest post_htmls by post_id
func (r *PostHTMLRepository) FindByPostID(ctx context.Context, postID interface{}) (*models.PostHTML, error) {
	var doc models.PostHTML
	if err := r.col.FindOne(ctx, bson.M{"post_id": postID}).Decode(&doc); err != nil {
		return nil, err
	}
	return &doc, nil
}

func NewPostHTMLRepository(db *mongo.Database) *PostHTMLRepository {
	return &PostHTMLRepository{col: db.Collection("post_htmls")}
}

// IsExistByPostID checks if a post_html exists for a given post_id
func (r *PostHTMLRepository) IsExistByPostID(ctx context.Context, postID interface{}) (bool, error) {
	err := r.col.FindOne(ctx, bson.M{"post_id": postID}).Err()
	if err == mongo.ErrNoDocuments {
		return false, nil
	}
	return err == nil, err
}

// Insert creates a new post_html document
func (r *PostHTMLRepository) Insert(ctx context.Context, h *models.PostHTML) (*mongo.InsertOneResult, error) {
	now := time.Now()
	if h.CreatedAt.IsZero() {
		h.CreatedAt = now
	}
	h.UpdatedAt = now
	return r.col.InsertOne(ctx, h)
}

// UpdateByPostID updates fields of post_html by post_id
func (r *PostHTMLRepository) UpdateByPostID(ctx context.Context, h *models.PostHTML) (*mongo.UpdateResult, error) {
	h.UpdatedAt = time.Now()
	filter := bson.M{"post_id": h.PostID}
	update := bson.M{"$set": bson.M{
		"updated_at":        h.UpdatedAt,
		"raw_html":          h.RawHTML,
		"fetched_at":        h.FetchedAt,
		"fetch_duration_ms": h.FetchDurationMs,
		"html_size_bytes":   h.HTMLSizeBytes,
		"blog_name":         h.BlogName,
		"post_title":        h.PostTitle,
	}}
	return r.col.UpdateOne(ctx, filter, update, options.Update())
}
