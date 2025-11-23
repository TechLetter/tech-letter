package repositories

import (
	"context"
	"regexp"
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

// IsExistByLink checks if a post exists by its link.
func (r *PostRepository) IsExistByLink(ctx context.Context, link string) (bool, error) {
	err := r.col.FindOne(ctx, bson.M{"link": link}).Err()
	if err == mongo.ErrNoDocuments {
		return false, nil
	}
	return err == nil, err
}

// Insert inserts a new post document.
func (r *PostRepository) Insert(ctx context.Context, p *models.Post) (*mongo.InsertOneResult, error) {
	now := time.Now()
	if p.CreatedAt.IsZero() {
		p.CreatedAt = now
	}
	p.UpdatedAt = now
	if p.Status == (models.StatusFlags{}) {
		p.Status = models.StatusFlags{}
	}
	return r.col.InsertOne(ctx, p)
}

// FindByLink returns a post by link
func (r *PostRepository) FindByLink(ctx context.Context, link string) (*models.Post, error) {
	var p models.Post
	if err := r.col.FindOne(ctx, bson.M{"link": link}).Decode(&p); err != nil {
		return nil, err
	}
	return &p, nil
}

// SetAISummarized updates only the status.ai_summarized flag and updated_at.
// 다른 상태 필드는 건드리지 않으므로, 향후 StatusFlags 필드가 늘어나더라도 안전하다.
func (r *PostRepository) SetAISummarized(ctx context.Context, postID interface{}, summarized bool) error {
	_, err := r.col.UpdateByID(ctx, postID, bson.M{
		"$set": bson.M{
			"status.ai_summarized": summarized,
			"updated_at":           time.Now(),
		},
	})
	return err
}

// UpdateAISummary sets normalized summary snapshot on the post document
func (r *PostRepository) UpdateAISummary(ctx context.Context, postID interface{}, summary models.AISummary) error {
	_, err := r.col.UpdateByID(ctx, postID, bson.M{
		"$set": bson.M{"aisummary": summary, "updated_at": time.Now()},
	})
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
	Page       int
	PageSize   int
	Categories []string
	Tags       []string
	BlogID     *primitive.ObjectID
	BlogName   string
}

// List returns posts with filters and pagination, sorted by published_at desc
func (r *PostRepository) List(ctx context.Context, opt ListPostsOptions) ([]models.Post, int64, error) {
	filter := bson.M{}
	// Build case-insensitive anchored regex arrays for categories and tags
	toRegexIn := func(values []string) []interface{} {
		arr := make([]interface{}, 0, len(values))
		for _, v := range values {
			if v == "" {
				continue
			}
			pattern := "^" + regexp.QuoteMeta(v) + "$"
			arr = append(arr, primitive.Regex{Pattern: pattern, Options: "i"})
		}
		return arr
	}

	catsRegex := toRegexIn(opt.Categories)
	tagsRegex := toRegexIn(opt.Tags)
	if len(catsRegex) > 0 && len(tagsRegex) > 0 {
		filter["$or"] = []bson.M{
			{"aisummary.categories": bson.M{"$in": catsRegex}},
			{"aisummary.tags": bson.M{"$in": tagsRegex}},
		}
	} else if len(catsRegex) > 0 {
		filter["aisummary.categories"] = bson.M{"$in": catsRegex}
	} else if len(tagsRegex) > 0 {
		filter["aisummary.tags"] = bson.M{"$in": tagsRegex}
	}

	// Blog filters
	if opt.BlogID != nil {
		filter["blog_id"] = *opt.BlogID
	}
	if opt.BlogName != "" {
		filter["blog_name"] = primitive.Regex{Pattern: "^" + regexp.QuoteMeta(opt.BlogName) + "$", Options: "i"}
	}

	if opt.Page <= 0 {
		opt.Page = 1
	}
	if opt.PageSize <= 0 || opt.PageSize > 100 {
		opt.PageSize = 20
	}
	skip := int64((opt.Page - 1) * opt.PageSize)
	limit := int64(opt.PageSize)

	total, err := r.col.CountDocuments(ctx, filter)
	if err != nil {
		return nil, 0, err
	}

	findOpts := options.Find().SetSkip(skip).SetLimit(limit).SetSort(bson.D{
		{Key: "published_at", Value: -1},
		{Key: "_id", Value: -1},
	})
	cur, err := r.col.Find(ctx, filter, findOpts)
	if err != nil {
		return nil, 0, err
	}
	defer cur.Close(ctx)

	var results []models.Post
	for cur.Next(ctx) {
		var p models.Post
		if err := cur.Decode(&p); err != nil {
			return nil, 0, err
		}
		results = append(results, p)
	}
	if err := cur.Err(); err != nil {
		return nil, 0, err
	}
	return results, total, nil
}

// FindByID returns a post by its ObjectID
func (r *PostRepository) FindByID(ctx context.Context, id primitive.ObjectID) (*models.Post, error) {
	var p models.Post
	if err := r.col.FindOne(ctx, bson.M{"_id": id}).Decode(&p); err != nil {
		return nil, err
	}
	return &p, nil
}

// IncrementViewCount increments the view_count field by 1 for the given post ID
func (r *PostRepository) IncrementViewCount(ctx context.Context, id primitive.ObjectID) error {
	_, err := r.col.UpdateByID(ctx, id, bson.M{
		"$inc": bson.M{"view_count": 1},
		"$set": bson.M{"updated_at": time.Now()},
	})
	return err
}

// FindUnsummarized 는 아직 AI 요약이 완료되지 않은 포스트들을 조회한다.
// Aggregate 서비스에서 요약 재시도를 트리거할 때 사용한다.
func (r *PostRepository) FindUnsummarized(ctx context.Context, limit int64) ([]models.Post, error) {
	filter := bson.M{"status.ai_summarized": false}
	findOpts := options.Find().SetLimit(limit).SetSort(bson.D{
		{Key: "created_at", Value: 1},
		{Key: "_id", Value: 1},
	})

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
