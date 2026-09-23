"""렌더러 — 차단 페이지 재시도 판정."""

from __future__ import annotations

from pathlib import Path

from techletter.summary.renderer import (
    RETRY_MARKER_MAX_HTML,
    needs_retry,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "html"


def test_a_challenge_page_triggers_a_retry() -> None:
    assert needs_retry((FIXTURES / "cloudflare.html").read_text(encoding="utf-8")) is True


def test_a_normal_article_does_not() -> None:
    assert needs_retry((FIXTURES / "article.html").read_text(encoding="utf-8")) is False


def test_markers_are_matched_case_insensitively() -> None:
    """마커 목록이 소문자여야 `html.lower()` 비교가 동작한다."""
    assert needs_retry("<p>VERIFYING YOU ARE HUMAN</p>") is True


def test_the_previously_dead_marker_now_works() -> None:
    assert needs_retry("<p>Out Of Nothing, Something.</p>") is True


def test_long_pages_are_not_treated_as_challenges() -> None:
    """긴 문서에 마커가 있으면 정상 글의 인용문일 확률이 높다."""
    html = "<p>본문</p>" * 20_000 + "just a moment"

    assert len(html) > RETRY_MARKER_MAX_HTML
    assert needs_retry(html) is False
