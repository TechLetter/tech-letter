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
		// published_at desc
		if _, err := d.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "published_at", Value: -1}},
			Options: options.Index().SetName("idx_published_at_desc"),
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
		// unique (blog_id, link)
		if _, err := d.Collection("posts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "blog_id", Value: 1}, {Key: "link", Value: 1}},
			Options: options.Index().SetName("uniq_blog_link").SetUnique(true),
		}); err != nil {
			return err
		}
	}

	// post_htmls: index on post_id
	{
		if _, err := d.Collection("post_htmls").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "post_id", Value: 1}},
			Options: options.Index().SetName("idx_post_id_html"),
		}); err != nil {
			return err
		}
	}

	// post_texts: index on post_id
	{
		if _, err := d.Collection("post_texts").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "post_id", Value: 1}},
			Options: options.Index().SetName("idx_post_id_text"),
		}); err != nil {
			return err
		}
	}

	// post_ai_summaries: indexes (no version uniqueness)
	{
		// index on ai_log_id for quick join
		if _, err := d.Collection("post_ai_summaries").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "ai_log_id", Value: 1}},
			Options: options.Index().SetName("idx_ai_log_id"),
		}); err != nil {
			return err
		}
		// index on post_id for retrieval of all summaries for a post
		if _, err := d.Collection("post_ai_summaries").Indexes().CreateOne(ctx, mongo.IndexModel{
			Keys:    bson.D{{Key: "post_id", Value: 1}},
			Options: options.Index().SetName("idx_post_id_summary"),
		}); err != nil {
			return err
		}
	}
	return nil
}
