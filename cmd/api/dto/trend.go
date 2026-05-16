package dto

import "time"

type RisingTrendPeriodDTO struct {
	From         time.Time `json:"from"`
	To           time.Time `json:"to"`
	PreviousFrom time.Time `json:"previous_from"`
	PreviousTo   time.Time `json:"previous_to"`
}

type RisingTagItemDTO struct {
	Tag           string   `json:"tag"`
	CurrentCount  int      `json:"current_count"`
	PreviousCount int      `json:"previous_count"`
	Delta         int      `json:"delta"`
	GrowthRate    *float64 `json:"growth_rate"`
}

type RisingTagsDTO struct {
	Period RisingTrendPeriodDTO `json:"period"`
	Items  []RisingTagItemDTO   `json:"items"`
}

type SeriesTrendPeriodDTO struct {
	From     time.Time `json:"from"`
	To       time.Time `json:"to"`
	Interval string    `json:"interval"`
}

type TrendSeriesPointDTO struct {
	Bucket    time.Time `json:"bucket"`
	PostCount int       `json:"post_count"`
	BlogCount int       `json:"blog_count"`
}

type TrendSeriesItemDTO struct {
	Tag    string                `json:"tag"`
	Points []TrendSeriesPointDTO `json:"points"`
}

type TrendSeriesDTO struct {
	Period SeriesTrendPeriodDTO `json:"period"`
	Series []TrendSeriesItemDTO `json:"series"`
}
