package repositories

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/mongo"

	"tech-letter/models"
)

type PostAISummaryRepository struct {
	col *mongo.Collection
}

func NewPostAISummaryRepository(db *mongo.Database) *PostAISummaryRepository {
	return &PostAISummaryRepository{col: db.Collection("post_ai_summaries")}
}

func (r *PostAISummaryRepository) Insert(ctx context.Context, doc models.PostAISummary) (*mongo.InsertOneResult, error) {
	now := time.Now()
	if doc.CreatedAt.IsZero() {
		doc.CreatedAt = now
	}
	doc.UpdatedAt = now
	return r.col.InsertOne(ctx, doc)
}
