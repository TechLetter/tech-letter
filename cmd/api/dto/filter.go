package dto

// FilterItem represents a single filter option with its count
type FilterItem struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

// CategoryFilterDTO represents the response for category filters
type CategoryFilterDTO struct {
	Items []FilterItem `json:"items"`
}

// TagFilterDTO represents the response for tag filters
type TagFilterDTO struct {
	Items []FilterItem `json:"items"`
}

// BlogFilterItem represents a blog filter option
type BlogFilterItem struct {
	ID    string `json:"id"`
	Name  string `json:"name"`
	Count int    `json:"count"`
}

// BlogFilterDTO represents the response for blog filters
type BlogFilterDTO struct {
	Items []BlogFilterItem `json:"items"`
}
