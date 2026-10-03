"""요약 파이프라인 — 페이지가 막히면 RSS 본문으로 대신한다."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError, RetryableError
from techletter.summary.pipeline import ContentPipeline, usable_feed_text

FEED_HTML = (
    "<html><body><article><p>" + "피드 본문 문장입니다. " * 120 + "</p></article></body></html>"
)


class FakeRenderer:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.attempts: list[int | None] = []

    async def render(self, url: str, *, attempts: int | None = None) -> str:
        self.attempts.append(attempts)
        raise self._error

    async def aclose(self) -> None:
        return None


def _pipeline(error: Exception) -> tuple[ContentPipeline, None]:
    renderer = FakeRenderer(error)
    pipeline = ContentPipeline(renderer)  # type: ignore[arg-type]
    pipeline.renderer_for_test = renderer  # type: ignore[attr-defined]
    return pipeline, None


@pytest.mark.parametrize(
    "error",
    [
        RetryableError("blocked after 3 render attempts"),
        PermanentError("bot challenge detected", reason="bot_blocked"),
    ],
)
async def test_a_blocked_page_falls_back_to_the_feed_body(error: Exception) -> None:
    pipeline, _ = _pipeline(error)

    fetched = await pipeline.fetch("https://example.com/a", FEED_HTML)

    assert "피드 본문" in fetched.plain_text


async def test_without_a_feed_body_the_failure_stands() -> None:
    pipeline, _ = _pipeline(RetryableError("blocked after 3 render attempts"))

    with pytest.raises(RetryableError):
        await pipeline.fetch("https://example.com/a", None)


async def test_a_non_blocking_failure_is_not_papered_over() -> None:
    """추출 자체가 안 되는 페이지는 피드로 덮지 않는다 — 원인이 다르다."""
    pipeline, _ = _pipeline(PermanentError("failed to extract", reason="extract_failed"))

    with pytest.raises(PermanentError):
        await pipeline.fetch("https://example.com/a", FEED_HTML)


async def test_a_feed_body_means_one_browser_attempt() -> None:
    """Medium은 서버에서 매번 막힌다. 대체 본문이 있으면 여러 번 열며 기다리지 않는다."""
    pipeline, _ = _pipeline(RetryableError("blocked after 1 render attempts"))

    await pipeline.fetch("https://example.com/a", FEED_HTML)

    assert pipeline.renderer_for_test.attempts == [1]  # type: ignore[attr-defined]


def test_a_feed_body_that_extracts_to_nothing_is_not_usable() -> None:
    """CMU 피드는 HTML이 9천 자인데 내용 없는 태그 틀뿐이라 추출하면 3자였다."""
    body = "<h4></h4><sup></sup><br /><p><em><em>&amp;</em></em></p>" * 150

    assert usable_feed_text(body) is None


def test_a_feed_body_that_fails_extraction_is_not_usable() -> None:
    """Go Blog 피드는 글 전체를 싣지만 추출기가 빈 문자열을 낸다. 잡을 죽이면 안 된다."""
    body = (
        '<div id="blog"><div id="content"><div class="Article"><h1>Title</h1>'
        + "<p>Go now has a portable SIMD package for vector code.</p>" * 40
        + "</div></div></div>"
    )

    assert usable_feed_text(body) is None


def test_a_truncated_feed_body_is_not_usable() -> None:
    body = "<p>" + "본문 문장입니다. " * 300 + "</p><p>Continue reading on Medium »</p>"

    assert usable_feed_text(body) is None


def test_a_full_feed_body_is_usable() -> None:
    assert usable_feed_text(FEED_HTML)


async def test_an_unusable_feed_body_does_not_cut_browser_attempts() -> None:
    pipeline, _ = _pipeline(RetryableError("blocked"))

    with pytest.raises(RetryableError):
        truncated = "<p>" + "본문 문장입니다. " * 300 + "</p><p>Continue reading on Medium »</p>"
        await pipeline.fetch("https://example.com/a", truncated)

    assert pipeline.renderer_for_test.attempts == [None]  # type: ignore[attr-defined]
