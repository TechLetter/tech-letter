package dto

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
