package dto

import "time"

// AdminPostDTO is a full representation of a post for admins.
// It mirrors the Python Post domain model structure closely.
type AdminPostDTO struct {
	ID           string                 `json:"id"`
	CreatedAt    time.Time              `json:"created_at"`
	UpdatedAt    time.Time              `json:"updated_at"`
	Status       AdminPostStatusDTO     `json:"status"`
	ViewCount    int64                  `json:"view_count"`
	BlogID       string                 `json:"blog_id"`
	BlogName     string                 `json:"blog_name"`
	Title        string                 `json:"title"`
	Link         string                 `json:"link"`
	PublishedAt  time.Time              `json:"published_at"`
	ThumbnailURL string                 `json:"thumbnail_url"`
	AISummary    *AdminAISummaryDTO     `json:"aisummary"`
	Embedding    *AdminPostEmbeddingDTO `json:"embedding,omitempty"`
}

type AdminPostStatusDTO struct {
	AISummarized bool `json:"ai_summarized"`
	Embedded     bool `json:"embedded"`
}

type AdminAISummaryDTO struct {
	Categories  []string  `json:"categories"`
	Tags        []string  `json:"tags"`
	Summary     string    `json:"summary"`
	ModelName   string    `json:"model_name"`
	GeneratedAt time.Time `json:"generated_at"`
}

type AdminPostEmbeddingDTO struct {
	ModelName       string    `json:"model_name"`
	CollectionName  string    `json:"collection_name"`
	VectorDimension int       `json:"vector_dimension"`
	ChunkCount      int       `json:"chunk_count"`
	EmbeddedAt      time.Time `json:"embedded_at"`
}

// PaginationAdminPostDTO is for swagger
// swagger:model PaginationAdminPostDTO
type PaginationAdminPostDTO struct {
	Data     []AdminPostDTO `json:"data"`
	Page     int            `json:"page"`
	PageSize int            `json:"page_size"`
	Total    int64          `json:"total"`
}
