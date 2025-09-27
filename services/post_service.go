package services

import (
    "context"

    "go.mongodb.org/mongo-driver/bson/primitive"
    "tech-letter/dto"
    "tech-letter/repositories"
)

// PostService encapsulates business logic for posts and DTO mapping
type PostService struct {
    repo *repositories.PostRepository
}

// GetByID loads a post by its ObjectID hex and returns a DTO
func (s *PostService) GetByID(ctx context.Context, hexID string) (*dto.PostDTO, error) {
    id, err := primitive.ObjectIDFromHex(hexID)
    if err != nil {
        return nil, err
    }
    p, err := s.repo.FindByID(ctx, id)
    if err != nil {
        return nil, err
    }
    d := dto.NewPostDTO(*p)
    return &d, nil
}

func NewPostService(repo *repositories.PostRepository) *PostService {
    return &PostService{repo: repo}
}

type ListPostsInput struct {
    Page       int
    PageSize   int
    Categories []string
    Tags       []string
    BlogID     string // hex string; optional
    BlogName   string // optional; case-insensitive exact match
}

func (s *PostService) List(ctx context.Context, in ListPostsInput) (dto.Pagination[dto.PostDTO], error) {
    var blogIDPtr *primitive.ObjectID
    if in.BlogID != "" {
        if oid, err := primitive.ObjectIDFromHex(in.BlogID); err == nil {
            blogIDPtr = &oid
        } else {
            // invalid blog_id input -> return empty page with total 0
            return dto.Pagination[dto.PostDTO]{Data: []dto.PostDTO{}, Page: in.Page, PageSize: in.PageSize, Total: 0}, nil
        }
    }

    items, total, err := s.repo.List(ctx, repositories.ListPostsOptions{
        Page:       in.Page,
        PageSize:   in.PageSize,
        Categories: in.Categories,
        Tags:       in.Tags,
        BlogID:     blogIDPtr,
        BlogName:   in.BlogName,
    })
    if err != nil {
        return dto.Pagination[dto.PostDTO]{}, err
    }
    out := make([]dto.PostDTO, 0, len(items))
    for _, p := range items {
        out = append(out, dto.NewPostDTO(p))
    }
    return dto.Pagination[dto.PostDTO]{
        Data:     out,
        Page:     in.Page,
        PageSize: in.PageSize,
        Total:    total,
    }, nil
}
