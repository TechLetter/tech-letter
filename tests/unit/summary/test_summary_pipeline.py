"""요약 파이프라인 — 페이지가 막히면 RSS 본문으로 대신한다."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError, RetryableError
from techletter.summary.pipeline import SummaryPipeline, usable_feed_text
from techletter.summary.summarizer import SummaryResult

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


class FakeSummarizer:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def summarize(self, plain_text: str) -> SummaryResult:
        self.inputs.append(plain_text)
        return SummaryResult(summary="요약", model_name="m")


def _pipeline(error: Exception) -> tuple[SummaryPipeline, FakeSummarizer]:
    summarizer = FakeSummarizer()
    renderer = FakeRenderer(error)
    pipeline = SummaryPipeline(renderer, summarizer)  # type: ignore[arg-type]
    pipeline.renderer_for_test = renderer  # type: ignore[attr-defined]
    return pipeline, summarizer


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


async def test_summarizing_uses_only_the_given_body() -> None:
    """요약 단계는 원문을 열지 않는다 — 저장된 본문만 쓴다."""
    pipeline, summarizer = _pipeline(AssertionError("renderer must not be called"))

    outcome = await pipeline.summarize("저장된 본문")

    assert outcome.summary == "요약"
    assert summarizer.inputs == ["저장된 본문"]


def test_a_feed_body_that_extracts_to_nothing_is_not_usable() -> None:
    """CMU 피드는 HTML이 9천 자인데 내용 없는 태그 틀뿐이라 추출하면 3자였다."""
    body = "<h4></h4><sup></sup><br /><p><em><em>&amp;</em></em></p>" * 150

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
