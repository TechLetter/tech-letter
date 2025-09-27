package dto

// Pagination is a generic pagination envelope for list results
// T is the element type of the Data slice
// Total represents the total number of items matching the filters (without pagination)
// Page is 1-based; PageSize is the requested page size
//
// Example: Pagination[PostDTO]
//
// Note: Generics require Go 1.18+
//
// swagger:model Pagination
// (Swagger generators may not fully support generics; handlers may need custom annotations.)
type Pagination[T any] struct {
    Data     []T   `json:"data"`
    Page     int   `json:"page"`
    PageSize int   `json:"page_size"`
    Total    int64 `json:"total"`
}
