package repositories

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"

	"tech-letter/models"
)

type BlogRepository struct {
	col *mongo.Collection
}

func NewBlogRepository(db *mongo.Database) *BlogRepository {
	return &BlogRepository{col: db.Collection("blogs")}
}

// UpsertByRSSURL upserts a blog document identified by its rss_url.
func (r *BlogRepository) UpsertByRSSURL(ctx context.Context, b *models.Blog) (*mongo.UpdateResult, error) {
	now := time.Now()
	if b.CreatedAt.IsZero() {
		b.CreatedAt = now
	}
	b.UpdatedAt = now

	filter := bson.M{"rss_url": b.RSSURL}
	update := bson.M{
		"$setOnInsert": bson.M{
			"created_at": b.CreatedAt,
		},
		"$set": bson.M{
			"updated_at": b.UpdatedAt,
			"name":       b.Name,
			"url":        b.URL,
			"rss_url":    b.RSSURL,
			"blog_type":  b.BlogType,
		},
	}
	opts := options.Update().SetUpsert(true)
	return r.col.UpdateOne(ctx, filter, update, opts)
}

// GetByRSSURL finds a blog by its rss_url.
func (r *BlogRepository) GetByRSSURL(ctx context.Context, rssURL string) (*models.Blog, error) {
	var b models.Blog
	if err := r.col.FindOne(ctx, bson.M{"rss_url": rssURL}).Decode(&b); err != nil {
		return nil, err
	}
	return &b, nil
}
