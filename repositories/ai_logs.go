package repositories

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/mongo"

	"tech-letter/models"
)

type AILogRepository struct {
	col *mongo.Collection
}

func NewAILogRepository(db *mongo.Database) *AILogRepository {
	return &AILogRepository{col: db.Collection("ai_logs")}
}

func (r *AILogRepository) Insert(ctx context.Context, log models.AILog) (*mongo.InsertOneResult, error) {
	if log.RequestedAt.IsZero() {
		log.RequestedAt = time.Now()
	}
	return r.col.InsertOne(ctx, log)
}
