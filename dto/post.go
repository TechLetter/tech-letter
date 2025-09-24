package dto

import (
    "time"
    "tech-letter/models"
)

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
    Categories   []string  `json:"categories"`
    Tags         []string  `json:"tags"`
    Summary      string    `json:"summary"`
}

// NewPostDTO constructs PostDTO from models.Post
func NewPostDTO(p models.Post) PostDTO {
    return PostDTO{
        ID:           p.ID.Hex(),
        BlogID:       p.BlogID.Hex(),
        BlogName:     p.BlogName,
        Title:        p.Title,
        Link:         p.Link,
        PublishedAt:  p.PublishedAt,
        ThumbnailURL: p.ThumbnailURL,
        Categories:   p.AISummary.Categories,
        Tags:         p.AISummary.Tags,
        Summary:      p.AISummary.Summary,
    }
}
