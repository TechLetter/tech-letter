package services

import (
	"context"
	"strings"

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
	BlogID             string
	StatusAISummarized *bool
	StatusEmbedded     *bool
}

// ListPosts retrieves a paginated list of posts for admin, mapping to AdminPostDTO
func (s *AdminService) ListPosts(ctx context.Context, in AdminListPostsInput) (dto.Pagination[dto.AdminPostDTO], error) {
	resp, err := s.contentClient.ListPosts(ctx, contentclient.ListPostsParams{
		Page:               in.Page,
		PageSize:           in.PageSize,
		BlogID:             in.BlogID,
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

// GrantCredit grants credits to a user with admin defaults (source, reason hardcoded).
func (s *AdminService) GrantCredit(ctx context.Context, userCode string, req *dto.GrantCreditRequestDTO) (*dto.GrantCreditResponseDTO, error) {
	// 비즈니스 로직: 어드민 크레딧 지급 시 source, reason 자동 설정
	internalReq := &dto.GrantCreditInternalRequest{
		Amount:    req.Amount,
		Source:    "admin",
		Reason:    "어드민 수동 지급",
		ExpiredAt: req.ExpiredAt,
	}
	return s.userClient.GrantCreditInternal(ctx, userCode, internalReq)
}

// -------------------- Chatbot Suggested Questions --------------------

func (s *AdminService) ListSuggestedQuestions(ctx context.Context) ([]dto.ChatbotSuggestedQuestionDTO, error) {
	return s.userClient.ListSuggestedQuestions(ctx, true)
}

func (s *AdminService) CreateSuggestedQuestion(ctx context.Context, req dto.ChatbotSuggestedQuestionMutationDTO) (dto.ChatbotSuggestedQuestionDTO, error) {
	req.Text = strings.TrimSpace(req.Text)
	return s.userClient.CreateSuggestedQuestion(ctx, req)
}

func (s *AdminService) UpdateSuggestedQuestion(ctx context.Context, id string, req dto.ChatbotSuggestedQuestionMutationDTO) (dto.ChatbotSuggestedQuestionDTO, error) {
	req.Text = strings.TrimSpace(req.Text)
	return s.userClient.UpdateSuggestedQuestion(ctx, id, req)
}

func (s *AdminService) DeleteSuggestedQuestion(ctx context.Context, id string) error {
	return s.userClient.DeleteSuggestedQuestion(ctx, id)
}

// -------------------- Blogs --------------------

func (s *AdminService) ListBlogs(ctx context.Context, page, pageSize int) (dto.Pagination[dto.AdminBlogDTO], error) {
	resp, err := s.contentClient.ListBlogs(ctx, contentclient.ListBlogsParams{
		Page:            page,
		PageSize:        pageSize,
		IncludeInactive: true,
	})
	if err != nil {
		return dto.Pagination[dto.AdminBlogDTO]{}, err
	}

	out := make([]dto.AdminBlogDTO, 0, len(resp.Items))
	for _, b := range resp.Items {
		out = append(out, mapAdminBlogFromContentService(b))
	}

	return dto.Pagination[dto.AdminBlogDTO]{
		Data:     out,
		Page:     page,
		PageSize: pageSize,
		Total:    int64(resp.Total),
	}, nil
}

func (s *AdminService) CreateBlog(ctx context.Context, req dto.BlogMutationRequestDTO) (dto.AdminBlogDTO, error) {
	blog, err := s.contentClient.CreateBlog(ctx, toContentBlogMutationRequest(req))
	if err != nil {
		return dto.AdminBlogDTO{}, err
	}
	return mapAdminBlogFromContentService(blog), nil
}

func (s *AdminService) UpdateBlog(ctx context.Context, id string, req dto.BlogMutationRequestDTO) (dto.AdminBlogDTO, error) {
	blog, err := s.contentClient.UpdateBlog(ctx, id, toContentBlogMutationRequest(req))
	if err != nil {
		return dto.AdminBlogDTO{}, err
	}
	return mapAdminBlogFromContentService(blog), nil
}

func (s *AdminService) DeleteBlog(ctx context.Context, id string, deletePosts bool) (dto.DeleteBlogResponseDTO, error) {
	resp, err := s.contentClient.DeleteBlog(ctx, id, deletePosts)
	if err != nil {
		return dto.DeleteBlogResponseDTO{}, err
	}

	message := "blog deleted successfully"
	if deletePosts {
		message = "blog and posts deleted successfully"
	}

	return dto.DeleteBlogResponseDTO{
		Message:      message,
		DeletedPosts: resp.DeletedPosts,
	}, nil
}

func toContentBlogMutationRequest(req dto.BlogMutationRequestDTO) contentclient.BlogMutationRequest {
	blogType := strings.TrimSpace(req.BlogType)
	if blogType == "" {
		blogType = "company"
	}
	return contentclient.BlogMutationRequest{
		Name:     strings.TrimSpace(req.Name),
		URL:      strings.TrimSpace(req.URL),
		RSSURL:   strings.TrimSpace(req.RSSURL),
		BlogType: blogType,
		IsActive: req.IsActive,
	}
}

func mapAdminBlogFromContentService(b contentclient.BlogItem) dto.AdminBlogDTO {
	return dto.AdminBlogDTO{
		ID:             b.ID,
		CreatedAt:      b.CreatedAt,
		UpdatedAt:      b.UpdatedAt,
		Name:           b.Name,
		URL:            b.URL,
		RSSURL:         b.RSSURL,
		BlogType:       b.BlogType,
		IsActive:       b.IsActive,
		LastFetchedAt:  b.LastFetchedAt,
		LastFetchError: b.LastFetchError,
		PostCount:      b.PostCount,
	}
}
