"""트렌드 집계 규칙."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from techletter.content.trends import TrendsService, normalize_tags, resolve_period
from techletter.core.errors import InvalidRequestError


class FakePosts:
    def __init__(
        self,
        windows: dict[tuple[datetime, datetime], list[dict[str, Any]]] | None = None,
        series: list[dict[str, Any]] | None = None,
    ) -> None:
        self._windows = windows or {}
        self._series = series or []
        self.window_calls: list[tuple[datetime, datetime]] = []

    async def tag_counts_between(self, published_from, published_to):
        self.window_calls.append((published_from, published_to))
        return self._windows.get((published_from, published_to), [])

    async def tag_series(self, tags, published_from, published_to, interval):
        return self._series


def row(tag: str, count: int) -> dict[str, Any]:
    return {"key": tag.lower(), "tag": tag, "count": count}


def test_period_lengths_match_the_current_service() -> None:
    for period, days in (("30d", 30), ("180d", 180), ("365d", 365), ("3y", 1095)):
        start, end = resolve_period(period)
        assert (end - start).days == days


def test_unknown_period_is_a_client_error() -> None:
    with pytest.raises(InvalidRequestError) as excinfo:
        resolve_period("7d")

    assert excinfo.value.status == 400
    assert "30d" in excinfo.value.details["allowed"]


def test_normalize_tags_dedupes_case_insensitively_keeping_order() -> None:
    assert normalize_tags([" Kafka ", "kafka", "Redis", ""]) == ["Kafka", "Redis"]


async def test_previous_window_is_the_same_length_immediately_before() -> None:
    posts = FakePosts()

    result = await TrendsService(posts).rising_tags("30d", 10)  # type: ignore[arg-type]

    assert result.previous_to == result.from_at
    assert result.from_at - result.previous_from == result.to - result.from_at
    assert len(posts.window_calls) == 2


async def test_growth_rate_is_undefined_for_a_brand_new_tag() -> None:
    posts = FakePosts()
    service = TrendsService(posts)  # type: ignore[arg-type]
    current, previous = None, None

    async def windows(published_from, published_to):
        nonlocal current, previous
        if current is None:
            current = (published_from, published_to)
            return [row("MCP", 12)]
        previous = (published_from, published_to)
        return []

    posts.tag_counts_between = windows  # type: ignore[method-assign]
    result = await service.rising_tags("30d", 10)

    (item,) = result.items
    assert item.previous_count == 0
    assert item.delta == 12
    assert item.growth_rate is None


async def test_growth_rate_is_rounded_to_one_decimal() -> None:
    calls = iter([[row("Rust", 7)], [row("Rust", 3)]])
    posts = FakePosts()
    posts.tag_counts_between = lambda *_: _next(calls)  # type: ignore[method-assign]

    result = await TrendsService(posts).rising_tags("30d", 10)  # type: ignore[arg-type]

    (item,) = result.items
    assert item.delta == 4
    assert item.growth_rate == 133.3


async def test_ranked_by_delta_then_current_count_then_name() -> None:
    calls = iter(
        [
            [row("bravo", 5), row("Alpha", 5), row("Charlie", 9)],
            [row("Charlie", 4)],
        ]
    )
    posts = FakePosts()
    posts.tag_counts_between = lambda *_: _next(calls)  # type: ignore[method-assign]

    result = await TrendsService(posts).rising_tags("30d", 10)  # type: ignore[arg-type]

    # 셋 다 delta=5 동률. 다음 기준인 current_count 로 Charlie(9)가 앞서고,
    # 남은 Alpha/bravo(5)는 대소문자를 무시한 이름순으로 갈린다.
    assert [item.tag for item in result.items] == ["Charlie", "Alpha", "bravo"]


async def test_limit_is_applied_after_ranking() -> None:
    calls = iter([[row("a", 1), row("b", 9)], []])
    posts = FakePosts()
    posts.tag_counts_between = lambda *_: _next(calls)  # type: ignore[method-assign]

    result = await TrendsService(posts).rising_tags("30d", 1)  # type: ignore[arg-type]

    assert [item.tag for item in result.items] == ["b"]


async def test_limit_below_one_still_returns_one_item() -> None:
    calls = iter([[row("a", 1)], []])
    posts = FakePosts()
    posts.tag_counts_between = lambda *_: _next(calls)  # type: ignore[method-assign]

    result = await TrendsService(posts).rising_tags("30d", 0)  # type: ignore[arg-type]

    assert len(result.items) == 1


async def test_bad_interval_is_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        await TrendsService(FakePosts()).tag_series(["kafka"], "30d", "hour")  # type: ignore[arg-type]


async def test_requested_tags_without_data_keep_an_empty_series() -> None:
    """차트 범례가 요청한 태그 수만큼 유지돼야 한다."""
    posts = FakePosts(
        series=[
            {
                "key": "kafka",
                "tag": "Kafka",
                "bucket": datetime(2025, 1, 1, tzinfo=UTC),
                "post_count": 3,
                "blog_count": 2,
            }
        ]
    )

    result = await TrendsService(posts).tag_series(["kafka", "redis"], "30d", "day")  # type: ignore[arg-type]

    assert [s.tag for s in result.series] == ["Kafka", "redis"]
    assert len(result.series[0].points) == 1
    assert result.series[1].points == []


async def test_display_name_comes_from_stored_documents() -> None:
    posts = FakePosts(
        series=[
            {
                "key": "kafka",
                "tag": "Apache Kafka",
                "bucket": datetime(2025, 1, 1, tzinfo=UTC),
                "post_count": 1,
                "blog_count": 1,
            }
        ]
    )

    result = await TrendsService(posts).tag_series(["KAFKA"], "30d", "week")  # type: ignore[arg-type]

    assert result.series[0].tag == "Apache Kafka"
    assert result.interval == "week"


def _next(calls):
    """iterator 를 코루틴처럼 쓰기 위한 어댑터."""

    async def _coro():
        return next(calls)

    return _coro()


def test_period_window_ends_at_now() -> None:
    start, end = resolve_period("30d")

    assert end - datetime.now(UTC) < timedelta(seconds=5)
    assert start < end
