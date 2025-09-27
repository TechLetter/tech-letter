package services

import (
    "context"

    "tech-letter/dto"
    "tech-letter/repositories"
)

// BlogService encapsulates business logic for blogs and DTO mapping
type BlogService struct {
    repo *repositories.BlogRepository
}

func NewBlogService(repo *repositories.BlogRepository) *BlogService {
    return &BlogService{repo: repo}
}

type ListBlogsInput struct {
    Page     int
    PageSize int
}

func (s *BlogService) List(ctx context.Context, in ListBlogsInput) (dto.Pagination[dto.BlogDTO], error) {
    items, total, err := s.repo.List(ctx, repositories.ListBlogsOptions{
        Page:     in.Page,
        PageSize: in.PageSize,
    })
    if err != nil {
        return dto.Pagination[dto.BlogDTO]{}, err
    }
    out := make([]dto.BlogDTO, 0, len(items))
    for _, b := range items {
        out = append(out, dto.NewBlogDTO(b))
    }
    return dto.Pagination[dto.BlogDTO]{
        Data:     out,
        Page:     in.Page,
        PageSize: in.PageSize,
        Total:    total,
    }, nil
}
