package services

import (
	"context"

	"tech-letter/cmd/api/clients/contentclient"
	"tech-letter/cmd/api/dto"
)

type TrendService struct {
	client *contentclient.Client
}

func NewTrendService(client *contentclient.Client) *TrendService {
	return &TrendService{client: client}
}

func (s *TrendService) GetRisingTags(ctx context.Context, period string, limit int) (dto.RisingTagsDTO, error) {
	resp, err := s.client.GetRisingTags(ctx, contentclient.TrendParams{
		Period: period,
		Limit:  limit,
	})
	if err != nil {
		return dto.RisingTagsDTO{}, err
	}

	items := make([]dto.RisingTagItemDTO, 0, len(resp.Items))
	for _, item := range resp.Items {
		items = append(items, dto.RisingTagItemDTO{
			Tag:           item.Tag,
			CurrentCount:  item.CurrentCount,
			PreviousCount: item.PreviousCount,
			Delta:         item.Delta,
			GrowthRate:    item.GrowthRate,
		})
	}

	return dto.RisingTagsDTO{
		Period: dto.RisingTrendPeriodDTO{
			From:         resp.Period.From,
			To:           resp.Period.To,
			PreviousFrom: resp.Period.PreviousFrom,
			PreviousTo:   resp.Period.PreviousTo,
		},
		Items: items,
	}, nil
}

func (s *TrendService) GetSeries(ctx context.Context, tags []string, period string, interval string) (dto.TrendSeriesDTO, error) {
	resp, err := s.client.GetTrendSeries(ctx, contentclient.TrendSeriesParams{
		Tags:     tags,
		Period:   period,
		Interval: interval,
	})
	if err != nil {
		return dto.TrendSeriesDTO{}, err
	}

	series := make([]dto.TrendSeriesItemDTO, 0, len(resp.Series))
	for _, item := range resp.Series {
		points := make([]dto.TrendSeriesPointDTO, 0, len(item.Points))
		for _, point := range item.Points {
			points = append(points, dto.TrendSeriesPointDTO{
				Bucket:    point.Bucket,
				PostCount: point.PostCount,
				BlogCount: point.BlogCount,
			})
		}
		series = append(series, dto.TrendSeriesItemDTO{
			Tag:    item.Tag,
			Points: points,
		})
	}

	return dto.TrendSeriesDTO{
		Period: dto.SeriesTrendPeriodDTO{
			From:     resp.Period.From,
			To:       resp.Period.To,
			Interval: resp.Period.Interval,
		},
		Series: series,
	}, nil
}

func (s *TrendService) ListPosts(ctx context.Context, tags []string, period string, page int, pageSize int) (dto.Pagination[dto.PostDTO], error) {
	resp, err := s.client.ListTrendPosts(ctx, contentclient.TrendPostsParams{
		Tags:     tags,
		Period:   period,
		Page:     page,
		PageSize: pageSize,
	})
	if err != nil {
		return dto.Pagination[dto.PostDTO]{}, err
	}

	items := make([]dto.PostDTO, 0, len(resp.Items))
	for _, post := range resp.Items {
		items = append(items, mapPostFromContentService(post))
	}

	return dto.Pagination[dto.PostDTO]{
		Data:     items,
		Page:     resp.Page,
		PageSize: resp.PageSize,
		Total:    int64(resp.Total),
	}, nil
}
