"""태그 트렌드 집계.

기간 정의는 현행 그대로다: `3y`는 1095일(=365*3)이고 윤년을 보정하지 않는다.
"직전 기간"은 현재 기간과 같은 길이만큼 앞으로 민 구간이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from techletter.core.errors import InvalidRequestError
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from techletter.content.models import Post
    from techletter.content.repositories import PostRepository
    from techletter.core.pagination import Page

__all__ = [
    "INTERVALS",
    "PERIOD_DAYS",
    "RisingTag",
    "RisingTags",
    "SeriesPoint",
    "TagSeries",
    "TrendSeries",
    "TrendsService",
    "normalize_tags",
    "resolve_period",
]

PERIOD_DAYS = {"30d": 30, "180d": 180, "365d": 365, "3y": 365 * 3}
INTERVALS = frozenset({"day", "week", "month"})


@dataclass(frozen=True, slots=True)
class RisingTag:
    tag: str
    current_count: int
    previous_count: int
    delta: int
    growth_rate: float | None


@dataclass(frozen=True, slots=True)
class RisingTags:
    from_at: datetime
    to: datetime
    previous_from: datetime
    previous_to: datetime
    items: list[RisingTag]


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    bucket: datetime
    post_count: int
    blog_count: int


@dataclass(frozen=True, slots=True)
class TagSeries:
    tag: str
    points: list[SeriesPoint] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TrendSeries:
    from_at: datetime
    to: datetime
    interval: str
    series: list[TagSeries]


def resolve_period(period: str) -> tuple[datetime, datetime]:
    days = PERIOD_DAYS.get(period)
    if days is None:
        raise InvalidRequestError(
            f"unsupported period: {period}",
            details={"allowed": sorted(PERIOD_DAYS)},
        )
    now = utcnow()
    return now - timedelta(days=days), now


def normalize_tags(tags: list[str]) -> list[str]:
    """공백을 제거하고 대소문자 기준으로 중복을 없앤다. 입력 순서는 유지한다."""
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


class TrendsService:
    def __init__(self, posts: PostRepository) -> None:
        self._posts = posts

    async def rising_tags(self, period: str, limit: int) -> RisingTags:
        current_from, current_to = resolve_period(period)
        duration = current_to - current_from
        previous_from, previous_to = current_from - duration, current_from

        current_rows = await self._posts.tag_counts_between(current_from, current_to)
        previous_rows = await self._posts.tag_counts_between(previous_from, previous_to)
        previous_counts = {row["key"]: row["count"] for row in previous_rows}

        items = []
        for row in current_rows:
            current_count = int(row["count"])
            previous_count = int(previous_counts.get(row["key"], 0))
            delta = current_count - previous_count
            items.append(
                RisingTag(
                    tag=str(row["tag"]),
                    current_count=current_count,
                    previous_count=previous_count,
                    delta=delta,
                    # 직전 기간에 없던 태그는 증가율을 정의할 수 없다(0으로 나눔).
                    growth_rate=round(delta / previous_count * 100, 1) if previous_count else None,
                )
            )
        items.sort(key=lambda item: (-item.delta, -item.current_count, item.tag.lower()))

        return RisingTags(
            from_at=current_from,
            to=current_to,
            previous_from=previous_from,
            previous_to=previous_to,
            items=items[: max(1, limit)],
        )

    async def tag_series(self, tags: list[str], period: str, interval: str) -> TrendSeries:
        if interval not in INTERVALS:
            raise InvalidRequestError(
                f"unsupported interval: {interval}", details={"allowed": sorted(INTERVALS)}
            )
        published_from, published_to = resolve_period(period)
        wanted = normalize_tags(tags)
        rows = await self._posts.tag_series(wanted, published_from, published_to, interval)

        points: dict[str, list[SeriesPoint]] = {}
        # 표시 이름은 요청한 표기를 기본으로 하되, DB에 실제로 저장된 표기가 있으면 그것을 쓴다.
        display = {tag.lower(): tag for tag in wanted}
        for row in rows:
            key = str(row["key"])
            display[key] = str(row["tag"])
            points.setdefault(key, []).append(
                SeriesPoint(
                    bucket=row["bucket"],
                    post_count=int(row["post_count"]),
                    blog_count=int(row["blog_count"]),
                )
            )

        return TrendSeries(
            from_at=published_from,
            to=published_to,
            interval=interval,
            # 요청한 태그는 데이터가 없어도 빈 시계열로 남긴다(차트 범례 유지).
            series=[
                TagSeries(tag=display.get(tag.lower(), tag), points=points.get(tag.lower(), []))
                for tag in wanted
            ],
        )

    async def list_posts(self, tags: list[str], period: str, page: Page) -> tuple[list[Post], int]:
        from techletter.content.models import ListPostsFilter  # noqa: PLC0415

        published_from, published_to = resolve_period(period)
        return await self._posts.list_posts(
            ListPostsFilter(
                tags=normalize_tags(tags),
                published_from=published_from,
                published_to=published_to,
                summarized=True,
            ),
            page,
        )
