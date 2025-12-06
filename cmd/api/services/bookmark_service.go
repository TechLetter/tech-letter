package services

import (
	"context"

	"tech-letter/cmd/api/clients/contentclient"
	"tech-letter/cmd/api/clients/userclient"
	"tech-letter/cmd/api/dto"
)

// BookmarkService는 유저 북마크와 관련된 비즈니스 로직을 담당한다.
// - user-service의 북마크 API를 호출해 북마크 상태를 조회/변경한다.
// - content-service의 Post 데이터를 조합해 공개용 PostDTO 목록을 만든다.
type BookmarkService struct {
	contentClient *contentclient.Client
	userClient    *userclient.Client
}

func NewBookmarkService(contentClient *contentclient.Client, userClient *userclient.Client) *BookmarkService {
	return &BookmarkService{
		contentClient: contentClient,
		userClient:    userClient,
	}
}

// AddBookmark는 주어진 유저와 포스트에 대한 북마크를 추가한다.
func (s *BookmarkService) AddBookmark(ctx context.Context, userCode, postID string) error {
	_, err := s.userClient.AddBookmark(ctx, userCode, postID)
	return err
}

// RemoveBookmark는 주어진 유저와 포스트에 대한 북마크를 삭제한다.
func (s *BookmarkService) RemoveBookmark(ctx context.Context, userCode, postID string) error {
	return s.userClient.RemoveBookmark(ctx, userCode, postID)
}

// ListBookmarkedPosts는 유저의 북마크 포스트들을 페이지네이션하여 반환한다.
// 반환 형식은 /posts 목록과 동일한 Pagination[PostDTO] 이다.
func (s *BookmarkService) ListBookmarkedPosts(ctx context.Context, userCode string, page, pageSize int) (dto.Pagination[dto.PostDTO], error) {
	bookmarks, err := s.userClient.ListBookmarks(ctx, userCode, page, pageSize)
	if err != nil {
		return dto.Pagination[dto.PostDTO]{}, err
	}

	if len(bookmarks.Items) == 0 {
		return dto.Pagination[dto.PostDTO]{
			Data:     []dto.PostDTO{},
			Page:     page,
			PageSize: pageSize,
			Total:    int64(bookmarks.Total),
		}, nil
	}

	ids := make([]string, 0, len(bookmarks.Items))
	for _, b := range bookmarks.Items {
		ids = append(ids, b.PostID)
	}

	postsResp, err := s.contentClient.GetPostsBatch(ctx, ids)
	if err != nil {
		return dto.Pagination[dto.PostDTO]{}, err
	}

	byID := make(map[string]contentclient.PostItem, len(postsResp.Items))
	for _, p := range postsResp.Items {
		byID[p.ID] = p
	}

	out := make([]dto.PostDTO, 0, len(ids))
	for _, id := range ids {
		if p, ok := byID[id]; ok {
			d := mapPostFromContentService(p)
			v := true
			d.IsBookmarked = &v
			out = append(out, d)
		}
	}

	return dto.Pagination[dto.PostDTO]{
		Data:     out,
		Page:     page,
		PageSize: pageSize,
		Total:    int64(bookmarks.Total),
	}, nil
}

// MarkBookmarked는 주어진 포스트 목록에 대해 유저가 북마크한 포스트에 is_bookmarked 플래그를 채운다.
// - posts는 /posts 목록 조회 결과이며, 이 함수는 동일 길이의 새로운 슬라이스를 반환한다.
func (s *BookmarkService) MarkBookmarked(ctx context.Context, userCode string, posts []dto.PostDTO) ([]dto.PostDTO, error) {
	if len(posts) == 0 {
		return posts, nil
	}

	ids := make([]string, 0, len(posts))
	for _, p := range posts {
		ids = append(ids, p.ID)
	}

	resp, err := s.userClient.CheckBookmarks(ctx, userCode, ids)
	if err != nil {
		return nil, err
	}

	bookmarked := make(map[string]struct{}, len(resp.BookmarkedPostIDs))
	for _, id := range resp.BookmarkedPostIDs {
		bookmarked[id] = struct{}{}
	}

	out := make([]dto.PostDTO, len(posts))
	for i, p := range posts {
		d := p
		if _, ok := bookmarked[p.ID]; ok {
			v := true
			d.IsBookmarked = &v
		} else {
			v := false
			d.IsBookmarked = &v
		}
		out[i] = d
	}

	return out, nil
}
