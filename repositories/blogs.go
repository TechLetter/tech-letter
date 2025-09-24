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

// ListBlogsOptions defines pagination options for listing blogs
type ListBlogsOptions struct {
	Page     int
	PageSize int
}

// List returns blogs with simple pagination, sorted by name asc
func (r *BlogRepository) List(ctx context.Context, opt ListBlogsOptions) ([]models.Blog, error) {
	if opt.Page <= 0 {
		opt.Page = 1
	}
	if opt.PageSize <= 0 || opt.PageSize > 100 {
		opt.PageSize = 20
	}
	skip := int64((opt.Page - 1) * opt.PageSize)
	limit := int64(opt.PageSize)

	findOpts := options.Find().SetSkip(skip).SetLimit(limit).SetSort(bson.D{{Key: "name", Value: 1}})
	cur, err := r.col.Find(ctx, bson.M{}, findOpts)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var results []models.Blog
	for cur.Next(ctx) {
		var b models.Blog
		if err := cur.Decode(&b); err != nil {
			return nil, err
		}
		results = append(results, b)
	}
	if err := cur.Err(); err != nil {
		return nil, err
	}
	return results, nil
}
