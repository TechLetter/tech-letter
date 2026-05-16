from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from content_service.app.services.trends_service import TrendsService


class FakePostRepository:
    def __init__(self) -> None:
        self._tag_count_calls = 0
        self.current_counts = [
            {"key": "rag", "tag": "RAG", "count": 8},
            {"key": "kubernetes", "tag": "Kubernetes", "count": 4},
        ]
        self.previous_counts = [
            {"key": "rag", "tag": "RAG", "count": 2},
            {"key": "kubernetes", "tag": "Kubernetes", "count": 5},
        ]
        self.series_rows: list[dict[str, Any]] = []

    def get_tag_counts_between(
        self, published_from: datetime, published_to: datetime
    ) -> list[dict[str, Any]]:
        self._tag_count_calls += 1
        if self._tag_count_calls == 1:
            return self.current_counts
        return self.previous_counts

    def get_tag_series(
        self,
        tags: list[str],
        published_from: datetime,
        published_to: datetime,
        interval: str,
    ) -> list[dict[str, Any]]:
        return self.series_rows


def test_get_rising_tags_sorts_by_delta_and_calculates_growth() -> None:
    service = TrendsService(FakePostRepository())

    result = service.get_rising_tags(period="90d", limit=1)

    assert len(result.items) == 1
    assert result.items[0].tag == "RAG"
    assert result.items[0].current_count == 8
    assert result.items[0].previous_count == 2
    assert result.items[0].delta == 6
    assert result.items[0].growth_rate == 300.0


def test_get_tag_series_deduplicates_tags_and_preserves_empty_series() -> None:
    repo = FakePostRepository()
    bucket = datetime(2026, 5, 1, tzinfo=timezone.utc)
    repo.series_rows = [
        {
            "key": "rag",
            "tag": "RAG",
            "bucket": bucket,
            "post_count": 3,
            "blog_count": 2,
        }
    ]
    service = TrendsService(repo)

    result = service.get_tag_series(
        tags=["rag", "RAG", "MCP"],
        period="90d",
        interval="week",
    )

    assert [item.tag for item in result.series] == ["RAG", "MCP"]
    assert result.series[0].points[0].post_count == 3
    assert result.series[1].points == []
