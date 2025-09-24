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
    Page     int
    PageSize int
    Categories []string
    Tags       []string
}

func (s *PostService) List(ctx context.Context, in ListPostsInput) ([]dto.PostDTO, error) {
    items, err := s.repo.List(ctx, repositories.ListPostsOptions{
        Page:     in.Page,
        PageSize: in.PageSize,
        Categories: in.Categories,
        Tags:       in.Tags,
    })
    if err != nil {
        return nil, err
    }
    out := make([]dto.PostDTO, 0, len(items))
    for _, p := range items {
        out = append(out, dto.NewPostDTO(p))
    }
    return out, nil
}
