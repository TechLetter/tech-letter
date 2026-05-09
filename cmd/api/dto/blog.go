package dto

import "time"

// BlogDTO exposes minimal blog fields to API consumers
// Mirrors only necessary fields from models.Blog
// id is hex string
// name and url are public
//
// Note: We intentionally hide rss_url and blog_type from API response
// to decouple internal ingestion details from clients.
type BlogDTO struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	URL  string `json:"url"`
}

type AdminBlogDTO struct {
	ID             string     `json:"id"`
	CreatedAt      time.Time  `json:"created_at"`
	UpdatedAt      time.Time  `json:"updated_at"`
	Name           string     `json:"name"`
	URL            string     `json:"url"`
	RSSURL         string     `json:"rss_url"`
	BlogType       string     `json:"blog_type"`
	IsActive       bool       `json:"is_active"`
	LastFetchedAt  *time.Time `json:"last_fetched_at"`
	LastFetchError *string    `json:"last_fetch_error"`
	PostCount      int        `json:"post_count"`
}

type BlogMutationRequestDTO struct {
	Name     string `json:"name" binding:"required"`
	URL      string `json:"url" binding:"required"`
	RSSURL   string `json:"rss_url" binding:"required"`
	BlogType string `json:"blog_type" binding:"omitempty,oneof=company creator"`
	IsActive bool   `json:"is_active"`
}

type DeleteBlogResponseDTO struct {
	Message      string `json:"message"`
	DeletedPosts int    `json:"deleted_posts"`
}

// PaginationAdminBlogDTO is a concrete swagger-friendly type for paginated admin blogs response
type PaginationAdminBlogDTO = Pagination[AdminBlogDTO]
