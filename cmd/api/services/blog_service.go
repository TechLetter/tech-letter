package services

import (
	"context"

	"tech-letter/cmd/api/contentclient"
	"tech-letter/cmd/api/dto"
)

// BlogService encapsulates business logic for blogs and DTO mapping.
//
// - client: Python content-service HTTP API를 호출해 블로그 목록을 조회한다.
type BlogService struct {
	client *contentclient.Client
}

func NewBlogService(client *contentclient.Client) *BlogService {
	return &BlogService{client: client}
}

type ListBlogsInput struct {
	Page     int
	PageSize int
}

func (s *BlogService) List(ctx context.Context, in ListBlogsInput) (dto.Pagination[dto.BlogDTO], error) {
	resp, err := s.client.ListBlogs(ctx, contentclient.ListBlogsParams{
		Page:     in.Page,
		PageSize: in.PageSize,
	})
	if err != nil {
		return dto.Pagination[dto.BlogDTO]{}, err
	}
	out := make([]dto.BlogDTO, 0, len(resp.Items))
	for _, b := range resp.Items {
		out = append(out, mapBlogFromContentService(b))
	}
	return dto.Pagination[dto.BlogDTO]{
		Data:     out,
		Page:     in.Page,
		PageSize: in.PageSize,
		Total:    int64(resp.Total),
	}, nil
}

// mapBlogFromContentService converts content-service BlogItem into public BlogDTO.
func mapBlogFromContentService(b contentclient.BlogItem) dto.BlogDTO {
	return dto.BlogDTO{
		ID:   b.ID,
		Name: b.Name,
		URL:  b.URL,
	}
}
