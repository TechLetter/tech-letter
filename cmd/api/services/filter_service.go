package services

import (
	"context"

	"tech-letter/cmd/api/clients/contentclient"
	"tech-letter/cmd/api/dto"
)

// FilterService handles filter-related business logic
type FilterService struct {
	client *contentclient.Client
}

// NewFilterService creates a new FilterService instance
func NewFilterService(client *contentclient.Client) *FilterService {
	return &FilterService{client: client}
}

// GetCategoryFilters retrieves category filter statistics
func (s *FilterService) GetCategoryFilters(ctx context.Context, blogID string, tags []string) (dto.CategoryFilterDTO, error) {
	resp, err := s.client.GetCategoryFilters(ctx, contentclient.FilterParams{
		BlogID: blogID,
		Tags:   tags,
	})
	if err != nil {
		return dto.CategoryFilterDTO{}, err
	}

	items := make([]dto.FilterItem, len(resp.Items))
	for i, item := range resp.Items {
		items[i] = dto.FilterItem{
			Name:  item.Name,
			Count: item.Count,
		}
	}

	return dto.CategoryFilterDTO{Items: items}, nil
}

// GetTagFilters retrieves tag filter statistics
func (s *FilterService) GetTagFilters(ctx context.Context, blogID string, categories []string) (dto.TagFilterDTO, error) {
	resp, err := s.client.GetTagFilters(ctx, contentclient.FilterParams{
		BlogID:     blogID,
		Categories: categories,
	})
	if err != nil {
		return dto.TagFilterDTO{}, err
	}

	items := make([]dto.FilterItem, len(resp.Items))
	for i, item := range resp.Items {
		items[i] = dto.FilterItem{
			Name:  item.Name,
			Count: item.Count,
		}
	}

	return dto.TagFilterDTO{Items: items}, nil
}

// GetBlogFilters retrieves blog filter statistics
func (s *FilterService) GetBlogFilters(ctx context.Context, categories []string, tags []string) (dto.BlogFilterDTO, error) {
	resp, err := s.client.GetBlogFilters(ctx, contentclient.FilterParams{
		Categories: categories,
		Tags:       tags,
	})
	if err != nil {
		return dto.BlogFilterDTO{}, err
	}

	items := make([]dto.BlogFilterItem, len(resp.Items))
	for i, item := range resp.Items {
		items[i] = dto.BlogFilterItem{
			ID:    item.ID,
			Name:  item.Name,
			Count: item.Count,
		}
	}

	return dto.BlogFilterDTO{Items: items}, nil
}
