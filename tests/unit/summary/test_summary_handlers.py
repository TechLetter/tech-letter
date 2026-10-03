"""가져오기/요약 두 단계 핸들러 — 본문이 어디에 남고 다음 잡이 무엇인지."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from techletter.core.errors import PermanentError
from techletter.core.jobs.models import Job
from techletter.core.jobs.types import JobType
from techletter.explainer.models import Explainer, Tldr
from techletter.summary.handlers import ContentFetchHandler, SummaryRequestedHandler
from techletter.summary.pipeline import FetchedContent

REF = {"post_id": "p1", "title": "t", "link": "https://a.test/p1", "blog_name": "A"}


class FakePosts:
    def __init__(self, plain_text: str | None = None, feed_html: str | None = None) -> None:
        self.plain_text = plain_text
        self.feed_html = feed_html
        self.saved: list[tuple[str, str]] = []
        self.failures: list[str] = []
        self.dated: list[datetime] = []

    async def get_feed_html(self, post_id: str) -> str | None:
        return self.feed_html

    async def get_plain_text(self, post_id: str) -> str | None:
        return self.plain_text

    async def save_content(self, post_id: str, plain_text: str, thumbnail_url: str) -> bool:
        self.saved.append((plain_text, thumbnail_url))
        return True

    async def mark_summary_failed(self, post_id: str, reason: str) -> bool:
        self.failures.append(reason)
        return True

    async def correct_published_at(self, post_id: str, published_at: datetime) -> bool:
        self.dated.append(published_at)
        return True


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[JobType, dict[str, Any]]] = []

    async def enqueue(self, job_type, key, payload=None, **kwargs):
        self.enqueued.append((job_type, payload or {}))


class FakePipeline:
    def __init__(
        self, error: Exception | None = None, published_at: datetime | None = None
    ) -> None:
        self.error = error
        self.published_at = published_at
        self.fetched_with: list[str | None] = []

    async def fetch(self, url: str, feed_html: str | None = None) -> FetchedContent:
        self.fetched_with.append(feed_html)
        if self.error:
            raise self.error
        return FetchedContent(
            plain_text="본문", thumbnail_url="https://a.test/t.png", published_at=self.published_at
        )


class FakeExplainer:
    def __init__(self) -> None:
        self.explained: list[str] = []

    async def generate(self, post_id: str, title: str, blog_name: str, text: str) -> Explainer:
        self.explained.append(text)
        return Explainer(
            post_id="6a0000000000000000000001",  # type: ignore[arg-type]
            tldr=Tldr(one_liner="요약입니다.", points=["a", "b", "c"]),
            body_md="## 배경\n본문",
            categories=["모바일"],
        )


def job(job_type: JobType) -> Job:
    return Job(type=job_type, key="p1", payload=dict(REF))


async def test_a_fetch_stores_the_body_then_asks_for_a_summary() -> None:
    posts, queue, pipeline = FakePosts(feed_html="<p>피드</p>"), FakeQueue(), FakePipeline()

    await ContentFetchHandler(posts, pipeline, queue)(job(JobType.CONTENT_FETCH_REQUESTED))  # type: ignore[arg-type]

    assert pipeline.fetched_with == ["<p>피드</p>"]
    assert posts.saved == [("본문", "https://a.test/t.png")]
    assert [t for t, _ in queue.enqueued] == [JobType.SUMMARY_REQUESTED]


async def test_a_fetch_hands_the_page_date_to_the_repository() -> None:
    """피드에 날짜가 없던 글은 페이지 날짜로 바로잡는다 — 어느 글인지는 저장소가 가린다."""
    page_date = datetime(2026, 9, 24, tzinfo=UTC)
    posts, pipeline = FakePosts(), FakePipeline(published_at=page_date)

    await ContentFetchHandler(posts, pipeline, FakeQueue())(job(JobType.CONTENT_FETCH_REQUESTED))  # type: ignore[arg-type]

    assert posts.dated == [page_date]


async def test_a_blocked_fetch_never_reaches_the_llm() -> None:
    posts, queue = FakePosts(), FakeQueue()
    pipeline = FakePipeline(PermanentError("page not found", reason="not_found"))

    with pytest.raises(PermanentError):
        await ContentFetchHandler(posts, pipeline, queue)(job(JobType.CONTENT_FETCH_REQUESTED))  # type: ignore[arg-type]

    assert queue.enqueued == []
    assert posts.failures


async def test_an_explainer_uses_the_stored_body() -> None:
    posts, queue, explainer = FakePosts(plain_text="저장된 본문"), FakeQueue(), FakeExplainer()

    await SummaryRequestedHandler(posts, queue, explainer)(job(JobType.SUMMARY_REQUESTED))  # type: ignore[arg-type]

    assert explainer.explained == ["저장된 본문"]
    [(job_type, payload)] = queue.enqueued
    assert job_type == JobType.SUMMARY_COMPLETED
    assert set(payload) == {"post_id", "summary", "categories", "tags", "model_name", "explainer"}


async def test_an_explainer_without_a_body_fetches_first() -> None:
    """나누기 전에 걸려 있던 잡도 스스로 새 흐름을 탄다."""
    posts, queue, explainer = FakePosts(), FakeQueue(), FakeExplainer()

    await SummaryRequestedHandler(posts, queue, explainer)(job(JobType.SUMMARY_REQUESTED))  # type: ignore[arg-type]

    assert explainer.explained == []
    assert [t for t, _ in queue.enqueued] == [JobType.CONTENT_FETCH_REQUESTED]
