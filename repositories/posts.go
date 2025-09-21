package repositories

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"

	"tech-letter/models"
)

type PostRepository struct {
	col *mongo.Collection
}

func NewPostRepository(db *mongo.Database) *PostRepository {
	return &PostRepository{col: db.Collection("posts")}
}

// UpsertByBlogAndLink upserts a post uniquely identified by (blog_id, link)
func (r *PostRepository) UpsertByBlogAndLink(ctx context.Context, p *models.Post) (*mongo.UpdateResult, error) {
	now := time.Now()
	if p.CreatedAt.IsZero() {
		p.CreatedAt = now
	}
	p.UpdatedAt = now
	// Ensure status flags exist (default false)
	p.Status = models.StatusFlags{
		HTMLFetched:  p.Status.HTMLFetched,
		TextParsed:   p.Status.TextParsed,
		AISummarized: p.Status.AISummarized,
	}

	filter := bson.M{"blog_id": p.BlogID, "link": p.Link}
	update := bson.M{
		"$setOnInsert": bson.M{
			"created_at": p.CreatedAt,
		},
		"$set": bson.M{
			"updated_at":           p.UpdatedAt,
			"status":               p.Status,
			"view_count":           p.ViewCount,
			"blog_id":              p.BlogID,
			"blog_name":            p.BlogName,
			"title":                p.Title,
			"link":                 p.Link,
			"published_at":         p.PublishedAt,
			"thumbnail_url":        p.ThumbnailURL,
			"reading_time_minutes": p.ReadingTimeMinutes,
			"ai_generated_info":    p.AIGeneratedInfo,
		},
	}
	opts := options.Update().SetUpsert(true)
	return r.col.UpdateOne(ctx, filter, update, opts)
}

// FindByBlogAndLink returns a post by (blog_id, link)
func (r *PostRepository) FindByBlogAndLink(ctx context.Context, blogID interface{}, link string) (*models.Post, error) {
	var p models.Post
	if err := r.col.FindOne(ctx, bson.M{"blog_id": blogID, "link": link}).Decode(&p); err != nil {
		return nil, err
	}
	return &p, nil
}

// UpdateStatusFlags sets status flags and updated_at
func (r *PostRepository) UpdateStatusFlags(ctx context.Context, postID interface{}, flags models.StatusFlags) error {
	_, err := r.col.UpdateByID(ctx, postID, bson.M{
		"$set": bson.M{"status": flags, "updated_at": time.Now()},
	})
	return err
}

// UpdateAIGeneratedInfo sets ai_generated_info
func (r *PostRepository) UpdateAIGeneratedInfo(ctx context.Context, postID interface{}, info models.AIGeneratedInfo) error {
	set := bson.M{
		"ai_generated_info": info,
		"updated_at":        time.Now(),
	}
	_, err := r.col.UpdateByID(ctx, postID, bson.M{"$set": set})
	return err
}

// UpdateThumbnailURL sets thumbnail_url field
func (r *PostRepository) UpdateThumbnailURL(ctx context.Context, postID interface{}, url string) error {
	_, err := r.col.UpdateByID(ctx, postID, bson.M{
		"$set": bson.M{"thumbnail_url": url, "updated_at": time.Now()},
	})
	return err
}

type ListPostsOptions struct {
	Page         int
	PageSize     int
	Category     string
	Tag          string
	Q            string
	HTMLFetched  *bool
	TextParsed   *bool
	AISummarized *bool
}

// List returns posts with filters and pagination, sorted by published_at desc
func (r *PostRepository) List(ctx context.Context, opt ListPostsOptions) ([]models.Post, error) {
	filter := bson.M{}
	if opt.Category != "" {
		filter["ai_generated_info.categories"] = opt.Category
	}
	if opt.Tag != "" {
		filter["ai_generated_info.tags"] = opt.Tag
	}
	if opt.Q != "" {
		filter["$or"] = []bson.M{
			{"title": bson.M{"$regex": opt.Q, "$options": "i"}},
			{"ai_generated_info.summary_short": bson.M{"$regex": opt.Q, "$options": "i"}},
			{"ai_generated_info.summary_long": bson.M{"$regex": opt.Q, "$options": "i"}},
			{"blog_name": bson.M{"$regex": opt.Q, "$options": "i"}},
		}
	}
	if opt.HTMLFetched != nil {
		filter["status.html_fetched"] = *opt.HTMLFetched
	}
	if opt.TextParsed != nil {
		filter["status.text_parsed"] = *opt.TextParsed
	}
	if opt.AISummarized != nil {
		filter["status.ai_summarized"] = *opt.AISummarized
	}

	if opt.Page <= 0 {
		opt.Page = 1
	}
	if opt.PageSize <= 0 || opt.PageSize > 100 {
		opt.PageSize = 20
	}
	skip := int64((opt.Page - 1) * opt.PageSize)
	limit := int64(opt.PageSize)

	findOpts := options.Find().SetSkip(skip).SetLimit(limit).SetSort(bson.D{{Key: "published_at", Value: -1}})
	cur, err := r.col.Find(ctx, filter, findOpts)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var results []models.Post
	for cur.Next(ctx) {
		var p models.Post
		if err := cur.Decode(&p); err != nil {
			return nil, err
		}
		results = append(results, p)
	}
	if err := cur.Err(); err != nil {
		return nil, err
	}
	return results, nil
}

// FindByID returns a post by its ObjectID
func (r *PostRepository) FindByID(ctx context.Context, id primitive.ObjectID) (*models.Post, error) {
	var p models.Post
	if err := r.col.FindOne(ctx, bson.M{"_id": id}).Decode(&p); err != nil {
		return nil, err
	}
	return &p, nil
}
