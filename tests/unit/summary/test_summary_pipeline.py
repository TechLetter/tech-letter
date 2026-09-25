"""요약 파이프라인 — 페이지가 막히면 RSS 본문으로 대신한다."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError, RetryableError
from techletter.summary.pipeline import SummaryPipeline
from techletter.summary.summarizer import SummaryResult

FEED_HTML = (
    "<html><body><article><p>" + "피드 본문 문장입니다. " * 50 + "</p></article></body></html>"
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
    pipeline, summarizer = _pipeline(error)

    outcome = await pipeline.run("https://example.com/a", FEED_HTML)

    assert outcome.summary == "요약"
    assert "피드 본문" in summarizer.inputs[0]


async def test_without_a_feed_body_the_failure_stands() -> None:
    pipeline, _ = _pipeline(RetryableError("blocked after 3 render attempts"))

    with pytest.raises(RetryableError):
        await pipeline.run("https://example.com/a", None)


async def test_a_non_blocking_failure_is_not_papered_over() -> None:
    """추출 자체가 안 되는 페이지는 피드로 덮지 않는다 — 원인이 다르다."""
    pipeline, _ = _pipeline(PermanentError("failed to extract", reason="extract_failed"))

    with pytest.raises(PermanentError):
        await pipeline.run("https://example.com/a", FEED_HTML)


async def test_a_feed_body_means_one_browser_attempt() -> None:
    """Medium은 서버에서 매번 막힌다. 대체 본문이 있으면 여러 번 열며 기다리지 않는다."""
    pipeline, _ = _pipeline(RetryableError("blocked after 1 render attempts"))

    await pipeline.run("https://example.com/a", FEED_HTML)

    assert pipeline.renderer_for_test.attempts == [1]  # type: ignore[attr-defined]
