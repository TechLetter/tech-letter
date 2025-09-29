package db

import (
	"context"
	"log"
	"os"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readpref"

	"tech-letter/config"
)

var (
	clientOnce sync.Once
	client     *mongo.Client
	db         *mongo.Database
)

// Init initializes the global Mongo client and database using config values.
func Init(ctx context.Context) error {
	var initErr error
	clientOnce.Do(func() {
		cfg := config.GetConfig()
		uri := cfg.MongoURI
		if uri == "" {
			if env := os.Getenv("MONGO_URI"); env != "" {
				uri = env
			}
		}
		if uri == "" {
			// Fallback for local docker-compose default
			uri = "mongodb://root:1234@localhost:27017/techletter?authSource=admin"
		}
		dbName := cfg.MongoDBName
		if dbName == "" {
			if env := os.Getenv("MONGO_DB_NAME"); env != "" {
				dbName = env
			}
		}
		if dbName == "" {
			dbName = "techletter"
		}

		cl, err := mongo.NewClient(options.Client().ApplyURI(uri))
		if err != nil {
			initErr = err
			return
		}
		ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
		defer cancel()
		if err := cl.Connect(ctx); err != nil {
			initErr = err
			return
		}
		// Ping to verify connection
		if err := cl.Ping(ctx, readpref.Primary()); err != nil {
			initErr = err
			return
		}
		client = cl
		db = client.Database(dbName)

		// Ensure indexes for all collections
		if err := ensureIndexes(ctx, db); err != nil {
			initErr = err
			return
		}
		log.Println("MongoDB connected and indexes ensured")
	})
	return initErr
}

func Client() *mongo.Client { return client }
func Database() *mongo.Database { return db }

func ensureIndexes(ctx context.Context, d *mongo.Database) error {
	// posts: indexes on published_at (desc), aisummary.categories, aisummary.tags
	{
		// published_at desc with _id for stable sorting
		if _, err := d.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "published_at", Value: -1}, {Key: "_id", Value: -1}},
			Options: options.Index().SetName("idx_published_at_id_desc"),
		}); err != nil {
			return err
		}
		// aisummary.categories
		if _, err := d.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "aisummary.categories", Value: 1}},
			Options: options.Index().SetName("idx_categories"),
		}); err != nil {
			return err
		}
		// aisummary.tags
		if _, err := d.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "aisummary.tags", Value: 1}},
			Options: options.Index().SetName("idx_tags"),
		}); err != nil {
			return err
		}
		// aisummary.tags with published_at for filtered sorting
		if _, err := d.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "aisummary.tags", Value: 1}, {Key: "published_at", Value: -1}},
			Options: options.Index().SetName("idx_tags_published_at"),
		}); err != nil {
			return err
		}
		// aisummary.categories with published_at for filtered sorting
		if _, err := d.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "aisummary.categories", Value: 1}, {Key: "published_at", Value: -1}},
			Options: options.Index().SetName("idx_categories_published_at"),
		}); err != nil {
			return err
		}
		// unique link
		if _, err := d.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "link", Value: 1}},
			Options: options.Index().SetName("uniq_link").SetUnique(true),
		}); err != nil {
			return err
		}
	}
	return nil
}
