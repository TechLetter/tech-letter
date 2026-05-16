from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from common.types.datetime import UtcDateTime


class TrendPeriodResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_at: UtcDateTime = Field(alias="from")
    to: UtcDateTime


class RisingTrendPeriodResponse(TrendPeriodResponse):
    previous_from: UtcDateTime
    previous_to: UtcDateTime


class SeriesTrendPeriodResponse(TrendPeriodResponse):
    interval: str


class RisingTagItem(BaseModel):
    tag: str
    current_count: int
    previous_count: int
    delta: int
    growth_rate: float | None = None


class RisingTagsResponse(BaseModel):
    period: RisingTrendPeriodResponse
    items: list[RisingTagItem] = Field(default_factory=list)


class TrendSeriesPoint(BaseModel):
    bucket: UtcDateTime
    post_count: int
    blog_count: int


class TrendSeriesItem(BaseModel):
    tag: str
    points: list[TrendSeriesPoint] = Field(default_factory=list)


class TrendSeriesResponse(BaseModel):
    period: SeriesTrendPeriodResponse
    series: list[TrendSeriesItem] = Field(default_factory=list)
