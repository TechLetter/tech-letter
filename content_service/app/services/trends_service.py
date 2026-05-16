from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends
from pymongo.database import Database

from common.models.post import ListPostsFilter, Post
from common.mongo.client import get_database

from ..api.schemas.trends import (
    RisingTagItem,
    RisingTagsResponse,
    RisingTrendPeriodResponse,
    SeriesTrendPeriodResponse,
    TrendSeriesItem,
    TrendSeriesPoint,
    TrendSeriesResponse,
)
from ..repositories.interfaces import PostRepositoryInterface
from ..repositories.post_repository import PostRepository


class TrendsService:
    """태그 기반 기술 트렌드 조회 비즈니스 로직."""

    _PERIOD_DAYS = {
        "30d": 30,
        "90d": 90,
        "180d": 180,
        "365d": 365,
    }
    _INTERVALS = {"day", "week", "month"}

    def __init__(self, repo: PostRepositoryInterface) -> None:
        self._repo = repo

    def get_rising_tags(self, period: str, limit: int) -> RisingTagsResponse:
        current_from, current_to = self._resolve_period(period)
        duration = current_to - current_from
        previous_from = current_from - duration
        previous_to = current_from

        current_rows = self._repo.get_tag_counts_between(current_from, current_to)
        previous_rows = self._repo.get_tag_counts_between(previous_from, previous_to)
        previous_counts = {
            str(row["key"]): int(row["count"]) for row in previous_rows
        }

        items: list[RisingTagItem] = []
        for row in current_rows:
            current_count = int(row["count"])
            previous_count = previous_counts.get(str(row["key"]), 0)
            delta = current_count - previous_count
            growth_rate = (
                round((delta / previous_count) * 100, 1)
                if previous_count > 0
                else None
            )
            items.append(
                RisingTagItem(
                    tag=str(row["tag"]),
                    current_count=current_count,
                    previous_count=previous_count,
                    delta=delta,
                    growth_rate=growth_rate,
                )
            )

        items.sort(
            key=lambda item: (-item.delta, -item.current_count, item.tag.lower())
        )
        limited_items = items[: max(1, limit)]

        return RisingTagsResponse(
            period=RisingTrendPeriodResponse(
                from_at=current_from,
                to=current_to,
                previous_from=previous_from,
                previous_to=previous_to,
            ),
            items=limited_items,
        )

    def get_tag_series(
        self, tags: list[str], period: str, interval: str
    ) -> TrendSeriesResponse:
        if interval not in self._INTERVALS:
            raise ValueError(f"unsupported trend interval: {interval}")

        published_from, published_to = self._resolve_period(period)
        normalized_tags = self._normalize_tags(tags)
        rows = self._repo.get_tag_series(
            normalized_tags,
            published_from,
            published_to,
            interval,
        )

        points_by_tag: dict[str, list[TrendSeriesPoint]] = {}
        display_names: dict[str, str] = {
            tag.lower(): tag for tag in normalized_tags
        }
        for row in rows:
            key = str(row["key"])
            display_names[key] = str(row["tag"])
            points_by_tag.setdefault(key, []).append(
                TrendSeriesPoint(
                    bucket=row["bucket"],
                    post_count=int(row["post_count"]),
                    blog_count=int(row["blog_count"]),
                )
            )

        series = [
            TrendSeriesItem(
                tag=display_names.get(tag.lower(), tag),
                points=points_by_tag.get(tag.lower(), []),
            )
            for tag in normalized_tags
        ]

        return TrendSeriesResponse(
            period=SeriesTrendPeriodResponse(
                from_at=published_from,
                to=published_to,
                interval=interval,
            ),
            series=series,
        )

    def list_trend_posts(
        self,
        tags: list[str],
        period: str,
        page: int,
        page_size: int,
    ) -> tuple[list[Post], int]:
        published_from, published_to = self._resolve_period(period)
        filter_ = ListPostsFilter(
            page=page,
            page_size=page_size,
            tags=self._normalize_tags(tags),
            published_from=published_from,
            published_to=published_to,
            status_ai_summarized=True,
        )
        return self._repo.list(filter_)

    def _resolve_period(self, period: str) -> tuple[datetime, datetime]:
        days = self._PERIOD_DAYS.get(period)
        if days is None:
            raise ValueError(f"unsupported trend period: {period}")

        now = datetime.now(timezone.utc)
        return now - timedelta(days=days), now

    def _normalize_tags(self, tags: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            value = tag.strip()
            key = value.lower()
            if not value or key in seen:
                continue
            normalized.append(value)
            seen.add(key)
        return normalized


def get_trends_service(
    db: Database = Depends(get_database),
) -> TrendsService:
    repo = PostRepository(db)
    return TrendsService(repo)
