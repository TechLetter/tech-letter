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

// SetThumbnailParsed updates only the status.thumbnail_parsed flag and updated_at.
// AISummarized와 마찬가지로, 다른 상태 필드는 건드리지 않는다.
func (r *PostRepository) SetThumbnailParsed(ctx context.Context, postID interface{}, parsed bool) error {
	_, err := r.col.UpdateByID(ctx, postID, bson.M{
		"$set": bson.M{
			"status.thumbnail_parsed": parsed,
			"updated_at":              time.Now(),
		},
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

// UpdateFields updates specific fields of a post
func (r *PostRepository) UpdateFields(ctx context.Context, id primitive.ObjectID, updates map[string]interface{}) error {
	update := bson.M{
		"$set": bson.M{
			"updated_at": time.Now(),
		},
	}
	for k, v := range updates {
		update["$set"].(bson.M)[k] = v
	}
	_, err := r.col.UpdateByID(ctx, id, update)
	return err
}

// FindPostsWithoutRenderedHTML RenderedHTML이 없거나 빈 문자열인 포스트 조회
// duration: 현재 시간으로부터 과거로 얼마나 떨어진 시점까지의 새로 추가된 데이터를 가져올지 결정하는 시간 간격
func (r *PostRepository) FindPostsWithoutRenderedHTML(ctx context.Context, limit int64, duration time.Duration) ([]models.Post, error) {
	targetTime := time.Now().Add(-duration)

	filter := bson.M{
		"$or": []bson.M{
			{"rendered_html": bson.M{"$exists": false}},
			{"rendered_html": ""},
		},
		"created_at": bson.M{"$lt": targetTime},
	}
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

// FindPostsWithoutThumbnail ThumbnailURL이 없거나 빈 문자열이지만 RenderedHTML은 있는 포스트 조회
// duration: 현재 시간으로부터 과거로 얼마나 떨어진 시점까지의 새로 추가된 데이터를 가져올지 결정하는 시간 간격
func (r *PostRepository) FindPostsWithoutThumbnail(ctx context.Context, limit int64, duration time.Duration) ([]models.Post, error) {

	// 현재 시간에서 입력받은 duration을 뺀 시점을 계산합니다.
	targetTime := time.Now().Add(-duration)

	filter := bson.M{
		"$and": []bson.M{
			{
				"$or": []bson.M{
					{"thumbnail_url": bson.M{"$exists": false}},
					{"thumbnail_url": ""},
				},
			},
			{"rendered_html": bson.M{"$exists": true, "$ne": ""}},
			{"created_at": bson.M{"$lt": targetTime}},
		},
	}

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

// FindPostsWithoutSummary AI 요약이 없지만 RenderedHTML은 있는 포스트 조회 (duration 인자 추가됨)
// duration: 현재 시간으로부터 과거로 얼마나 떨어진 시점까지의 새로 추가된 데이터를 가져올지 결정하는 시간 간격
func (r *PostRepository) FindPostsWithoutSummary(ctx context.Context, limit int64, duration time.Duration) ([]models.Post, error) {

	targetTime := time.Now().Add(-duration)

	filter := bson.M{
		"status.ai_summarized": false,
		"rendered_html":        bson.M{"$exists": true, "$ne": ""},
		"created_at":           bson.M{"$lt": targetTime},
	}

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
