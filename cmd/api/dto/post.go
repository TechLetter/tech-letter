package dto

import "time"

// PostDTO exposes the minimal fields needed for API consumers
// Fields are flattened from models.Post and models.AISummary
// ID and BlogID are hex strings to keep transport simple
// We intentionally hide internal processing fields like status flags, counters, etc.
type PostDTO struct {
	ID           string    `json:"id"`
	BlogID       string    `json:"blog_id"`
	BlogName     string    `json:"blog_name"`
	Title        string    `json:"title"`
	Link         string    `json:"link"`
	PublishedAt  time.Time `json:"published_at"`
	ThumbnailURL string    `json:"thumbnail_url"`
	ViewCount    int64     `json:"view_count"`
	Categories   []string  `json:"categories"`
	Tags         []string  `json:"tags"`
	Summary      string    `json:"summary"`
	IsBookmarked *bool     `json:"is_bookmarked,omitempty"`
}
