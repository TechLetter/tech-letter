"""원문 페이지에서 발행일 찾기."""

from __future__ import annotations

from datetime import UTC, datetime

from techletter.summary.published import extract_published_at

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def test_json_ld_date_published_wins() -> None:
    html = """<script type="application/ld+json">
    {"@context": "https://schema.org",
     "@graph": [{"@type": "BlogPosting", "datePublished": "2026-09-24"}]}
    </script><meta property="article:published_time" content="2026-01-01T00:00:00Z">"""

    assert extract_published_at(html, NOW) == datetime(2026, 9, 24, tzinfo=UTC)


def test_falls_back_to_the_published_time_meta() -> None:
    html = '<meta property="article:published_time" content="2026-09-20T09:30:00+09:00">'

    assert extract_published_at(html, NOW) == datetime(2026, 9, 20, 0, 30, tzinfo=UTC)


def test_ignores_future_or_missing_dates() -> None:
    future = '<meta property="article:published_time" content="2027-01-01">'

    assert extract_published_at(future, NOW) is None
    assert extract_published_at("<p>2026년 9월 1일에 쓴 글</p>", NOW) is None
