package services

import (
	"context"
	"errors"

	"tech-letter/cmd/api/clients/contentclient"
	"tech-letter/cmd/api/dto"
)

// PostService encapsulates business logic for posts and DTO mapping.
//
// - client: Python content-service HTTP API를 호출해 목록/단건/조회수 증가를 수행한다.
type PostService struct {
	client *contentclient.Client
}

// GetByID loads a post by its ObjectID hex and returns a DTO
func (s *PostService) GetByID(ctx context.Context, hexID string) (*dto.PostDTO, error) {
	p, err := s.client.GetPost(ctx, hexID)
	if err != nil {
		return nil, err
	}
	d := mapPostFromContentService(p)
	return &d, nil
}

func NewPostService(client *contentclient.Client) *PostService {
	return &PostService{client: client}
}

type ListPostsInput struct {
	Page       int
	PageSize   int
	Categories []string
	Tags       []string
	BlogID     string // hex string; optional
	BlogName   string // optional; case-insensitive exact match
	// Status Filters
	StatusAISummarized *bool
}

func (s *PostService) List(ctx context.Context, in ListPostsInput) (dto.Pagination[dto.PostDTO], error) {
	// blog_id 형식 검증은 content-service에서 수행되므로 여기서는 그대로 전달한다.
	resp, err := s.client.ListPosts(ctx, contentclient.ListPostsParams{
		Page:               in.Page,
		PageSize:           in.PageSize,
		Categories:         in.Categories,
		Tags:               in.Tags,
		BlogID:             in.BlogID,
		BlogName:           in.BlogName,
		StatusAISummarized: in.StatusAISummarized,
	})
	if err != nil {
		return dto.Pagination[dto.PostDTO]{}, err
	}
	out := make([]dto.PostDTO, 0, len(resp.Items))
	for _, p := range resp.Items {
		out = append(out, mapPostFromContentService(p))
	}
	return dto.Pagination[dto.PostDTO]{
		Data:     out,
		Page:     in.Page,
		PageSize: in.PageSize,
		Total:    int64(resp.Total),
	}, nil
}

// IncrementViewCount increments the view_count of a post by its ObjectID hex
func (s *PostService) IncrementViewCount(ctx context.Context, hexID string) error {
	// hexID는 content-service에서 유효성 검사를 수행하므로 여기서는 그대로 전달한다.
	if err := s.client.IncrementPostView(ctx, hexID); err != nil {
		if errors.Is(err, contentclient.ErrNotFound) {
			return err
		}
		return err
	}
	return nil
}

// mapPostFromContentService converts content-service PostItem into public PostDTO.
func mapPostFromContentService(p contentclient.PostItem) dto.PostDTO {
	return dto.PostDTO{
		ID:           p.ID,
		BlogID:       p.BlogID,
		BlogName:     p.BlogName,
		Title:        p.Title,
		Link:         p.Link,
		PublishedAt:  p.PublishedAt,
		ThumbnailURL: p.ThumbnailURL,
		ViewCount:    int64(p.ViewCount),
		Categories:   p.AISummary.Categories,
		Tags:         p.AISummary.Tags,
		Summary:      p.AISummary.Summary,
	}
}
