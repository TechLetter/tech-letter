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

// UpsertByPost updates or inserts by post_id
func (r *PostHTMLRepository) UpsertByPost(ctx context.Context, h *models.PostHTML) (*mongo.UpdateResult, error) {
	now := time.Now()
	if h.CreatedAt.IsZero() {
		h.CreatedAt = now
	}
	h.UpdatedAt = now

	filter := bson.M{"post_id": h.PostID}
	update := bson.M{
		"$setOnInsert": bson.M{"created_at": h.CreatedAt},
		"$set": bson.M{
			"updated_at":        h.UpdatedAt,
			"raw_html":          h.RawHTML,
			"fetched_at":        h.FetchedAt,
			"fetch_duration_ms": h.FetchDurationMs,
			"html_size_bytes":   h.HTMLSizeBytes,
			"blog_name":         h.BlogName,
			"post_title":        h.PostTitle,
		},
	}
	opts := options.Update().SetUpsert(true)
	return r.col.UpdateOne(ctx, filter, update, opts)
}
