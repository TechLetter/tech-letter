package services

import (
	"context"

	"tech-letter/cmd/api/clients/contentclient"
	"tech-letter/cmd/api/clients/userclient"
	"tech-letter/cmd/api/dto"
)

// AdminService encapsulates business logic for admin operations.
type AdminService struct {
	contentClient *contentclient.Client
	userClient    *userclient.Client
}

func NewAdminService(contentClient *contentclient.Client, userClient *userclient.Client) *AdminService {
	return &AdminService{
		contentClient: contentClient,
		userClient:    userClient,
	}
}

// -------------------- Posts --------------------

type AdminListPostsInput struct {
	Page               int
	PageSize           int
	StatusAISummarized *bool
	StatusEmbedded     *bool
}

// ListPosts retrieves a paginated list of posts for admin, mapping to AdminPostDTO
func (s *AdminService) ListPosts(ctx context.Context, in AdminListPostsInput) (dto.Pagination[dto.AdminPostDTO], error) {
	resp, err := s.contentClient.ListPosts(ctx, contentclient.ListPostsParams{
		Page:               in.Page,
		PageSize:           in.PageSize,
		StatusAISummarized: in.StatusAISummarized,
		StatusEmbedded:     in.StatusEmbedded,
	})
	if err != nil {
		return dto.Pagination[dto.AdminPostDTO]{}, err
	}

	out := make([]dto.AdminPostDTO, 0, len(resp.Items))
	for _, p := range resp.Items {
		d := dto.AdminPostDTO{
			ID:        p.ID,
			CreatedAt: p.CreatedAt,
			UpdatedAt: p.UpdatedAt,
			Status: dto.AdminPostStatusDTO{
				AISummarized: p.Status.AISummarized,
				Embedded:     p.Status.Embedded,
			},
			ViewCount:    int64(p.ViewCount),
			BlogID:       p.BlogID,
			BlogName:     p.BlogName,
			Title:        p.Title,
			Link:         p.Link,
			PublishedAt:  p.PublishedAt,
			ThumbnailURL: p.ThumbnailURL,
		}
		if p.AISummary != nil {
			d.AISummary = &dto.AdminAISummaryDTO{
				Categories:  p.AISummary.Categories,
				Tags:        p.AISummary.Tags,
				Summary:     p.AISummary.Summary,
				ModelName:   p.AISummary.ModelName,
				GeneratedAt: p.AISummary.GeneratedAt,
			}
		}
		if p.Embedding != nil {
			d.Embedding = &dto.AdminPostEmbeddingDTO{
				ModelName:       p.Embedding.ModelName,
				CollectionName:  p.Embedding.CollectionName,
				VectorDimension: p.Embedding.VectorDimension,
				ChunkCount:      p.Embedding.ChunkCount,
				EmbeddedAt:      p.Embedding.EmbeddedAt,
			}
		}
		out = append(out, d)
	}

	return dto.Pagination[dto.AdminPostDTO]{
		Data:     out,
		Page:     in.Page,
		PageSize: in.PageSize,
		Total:    int64(resp.Total),
	}, nil
}

// CreatePost creates a new post and returns the result.
func (s *AdminService) CreatePost(ctx context.Context, title, link, blogID string) (*contentclient.CreatePostResponse, error) {
	resp, err := s.contentClient.CreatePost(ctx, title, link, blogID)
	if err != nil {
		return nil, err
	}
	return &resp, nil
}

// DeletePost deletes a post by its ID.
func (s *AdminService) DeletePost(ctx context.Context, id string) error {
	return s.contentClient.DeletePost(ctx, id)
}

// TriggerSummary manually triggers AI summary for a post.
func (s *AdminService) TriggerSummary(ctx context.Context, id string) error {
	return s.contentClient.TriggerSummary(ctx, id)
}

// TriggerEmbedding manually triggers vector embedding for a post.
func (s *AdminService) TriggerEmbedding(ctx context.Context, id string) error {
	return s.contentClient.TriggerEmbedding(ctx, id)
}

// -------------------- Users --------------------

// ListUsers retrieves a paginated list of users.
func (s *AdminService) ListUsers(ctx context.Context, page, pageSize int) (userclient.ListUsersResponse, error) {
	return s.userClient.ListUsers(ctx, page, pageSize)
}

// -------------------- Blogs --------------------

// ListBlogs retrieves a paginated list of blogs via content-service.
// Although generic logic handles this, we can wrap it here if admin needs specific logic in future.
// For now, handlers can use BlogService directly, or we can mirror it here.
// Given the plan says "Update handlers to use AdminService", we should likely stick to
// moving ONLY explicitly admin things. Blog listing is used by public too?
// Actually ListBlogs in services is currently only in BlogService.
// Let's stick strictly to what was in PostService/AuthService for Admin.
