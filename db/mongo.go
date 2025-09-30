package db

import (
	"context"
	"fmt"
	"log"
	"os"
	"sync"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readpref"
	"go.mongodb.org/mongo-driver/x/mongo/driver/connstring"
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
		uri := os.Getenv("MONGO_URI")
		if uri == "" {
			initErr = fmt.Errorf("MONGO_URI environment variable is not set")
			return
		}

		cs, err := connstring.Parse(uri)
		if err != nil {
			initErr = err
			return
		}
		if cs.Database == "" {
			initErr = fmt.Errorf("MongoDB URI must include a database name")
			return
		}

		cl, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
		if err != nil {
			initErr = err
			return
		}
		if err := cl.Ping(ctx, readpref.Primary()); err != nil {
			initErr = err
			return
		}
		client = cl
		db = client.Database(cs.Database)

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
