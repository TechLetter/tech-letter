package dto

// PaginationPostDTO is a concrete swagger-friendly type for paginated posts response
// swagger:model PaginationPostDTO
type PaginationPostDTO struct {
    Data     []PostDTO `json:"data"`
    Page     int       `json:"page"`
    PageSize int       `json:"page_size"`
    Total    int64     `json:"total"`
}

// PaginationBlogDTO is a concrete swagger-friendly type for paginated blogs response
// swagger:model PaginationBlogDTO
type PaginationBlogDTO struct {
    Data     []BlogDTO `json:"data"`
    Page     int       `json:"page"`
    PageSize int       `json:"page_size"`
    Total    int64     `json:"total"`
}
