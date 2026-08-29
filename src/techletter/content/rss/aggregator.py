"""RSS 수집 오케스트레이션.

한 사이클: 활성 블로그를 돌며 피드를 읽고, 새 링크만 저장하고, 요약 잡을
넣는다. 블로그 하나가 실패해도 나머지는 계속 돈다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from techletter.content.jobs import enqueue_summary_requested
from techletter.content.models import AISummary, Post, StatusFlags
from techletter.core.errors import PermanentError
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.models import Blog
    from techletter.content.repositories import BlogRepository, PostRepository
    from techletter.content.rss.feeder import FeedItem, RssFeeder
    from techletter.core.jobs.queue import JobQueue

__all__ = ["AggregateResult", "Aggregator", "BlogResult"]

logger = get_logger(__name__)


@dataclass(slots=True)
class BlogResult:
    blog_id: str
    blog_name: str
    fetched: int = 0
    inserted: int = 0
    error: str | None = None
    deactivated: bool = False


@dataclass(slots=True)
class AggregateResult:
    blogs: list[BlogResult] = field(default_factory=list)

    @property
    def inserted(self) -> int:
        return sum(b.inserted for b in self.blogs)

    @property
    def failed(self) -> int:
        return sum(1 for b in self.blogs if b.error)


class Aggregator:
    def __init__(
        self,
        blogs: BlogRepository,
        posts: PostRepository,
        feeder: RssFeeder,
        queue: JobQueue,
        *,
        batch_size: int = 20,
        concurrency: int = 4,
        failure_threshold: int = 10,
    ) -> None:
        self._blogs = blogs
        self._posts = posts
        self._feeder = feeder
        self._queue = queue
        self._batch_size = batch_size
        self._concurrency = concurrency
        self._failure_threshold = failure_threshold

    async def run(self) -> AggregateResult:
        blogs = await self._blogs.list_active()
        if not blogs:
            logger.warning("no active blogs to collect")
            return AggregateResult()

        # 블로그를 몇 개씩 병렬로 처리한다. 전부 동시에 열면 나가는 커넥션이
        # 블로그 수만큼 늘어난다.
        semaphore = asyncio.Semaphore(self._concurrency)

        async def guarded(blog: Blog) -> BlogResult:
            async with semaphore:
                return await self._collect(blog)

        results = await asyncio.gather(*(guarded(blog) for blog in blogs))
        result = AggregateResult(blogs=list(results))
        logger.info(
            "rss cycle finished",
            extra={
                "blogs": len(blogs),
                "inserted": result.inserted,
                "failed_blogs": result.failed,
            },
        )
        return result

    async def _collect(self, blog: Blog) -> BlogResult:
        outcome = BlogResult(blog_id=str(blog.id), blog_name=blog.name)
        if blog.id is None:
            return outcome
        try:
            items = await self._feeder.fetch(
                blog.rss_url, limit=self._batch_size, tls_insecure=blog.tls_insecure
            )
        except Exception as exc:
            outcome.error = str(exc)
            failures = await self._blogs.record_fetch_result(blog.id, outcome.error)
            # 영구 실패(404 등)가 계속되는 피드는 자동으로 끈다. 현행은 끄지
            # 않아서 죽은 피드 4개가 30분마다 계속 에러를 냈다(ISSUE-005).
            if isinstance(exc, PermanentError) and failures >= self._failure_threshold:
                await self._blogs.deactivate(
                    blog.id, f"auto-disabled after {failures} failures: {outcome.error}"
                )
                outcome.deactivated = True
                logger.warning(
                    "blog auto-disabled",
                    extra={"blog": blog.name, "failures": failures},
                )
            else:
                logger.warning(
                    "rss fetch failed", extra={"blog": blog.name, "reason": outcome.error}
                )
            return outcome

        outcome.fetched = len(items)
        outcome.inserted = await self._store(blog, items)
        await self._blogs.record_fetch_result(blog.id, None)
        return outcome

    async def _store(self, blog: Blog, items: list[FeedItem]) -> int:
        known = await self._posts.existing_links([item.link for item in items])
        inserted = 0
        for item in items:
            if item.link in known:
                continue
            post = self._build(blog, item)
            saved = await self._posts.insert(post)
            if saved is None:  # 동시에 다른 워커가 넣었다.
                continue
            inserted += 1
            await enqueue_summary_requested(self._queue, saved)
        return inserted

    @staticmethod
    def _build(blog: Blog, item: FeedItem) -> Post:
        return Post(
            blog_id=blog.id,
            blog_name=blog.name,
            title=item.title,
            link=item.link,
            # 발행일이 없는 피드가 있다. 수집 시각을 쓰면 목록 정렬이 무너지지
            # 않는다(현행과 동일).
            published_at=item.published_at or utcnow(),
            thumbnail_url=None,
            status=StatusFlags(),
            # 요약 전에도 aisummary 키가 있어야 프론트의 옵셔널 체이닝이 단순해진다.
            aisummary=AISummary(),
        )
