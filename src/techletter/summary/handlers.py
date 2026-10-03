"""원문 확보·쉽게 읽기 잡 핸들러.

`content.fetch_requested` → 원문 확보·저장 → `summary.requested`
`summary.requested` → 저장된 본문으로 쉽게 읽기 → `summary.completed` 발행.
잡 이름은 예전 요약 시절 그대로 둔다(큐·인덱스·어드민 화면이 이 이름을 쓴다).
영구 실패면 포스트에 사유를 남긴다 — 어드민이 "왜 안 됐나"를 본다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.content.handlers import record_summary_failure
from techletter.content.jobs import (
    PostRefPayload,
    SummaryCompletedPayload,
    enqueue_content_fetch,
    enqueue_summary_requested,
)
from techletter.core.errors import PermanentError, QuotaExceededError
from techletter.core.jobs.types import JobType
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.repositories import PostRepository
    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue
    from techletter.explainer.generator import ExplainerGenerator
    from techletter.summary.pipeline import ContentPipeline

__all__ = ["ContentFetchHandler", "SummaryRequestedHandler"]

logger = get_logger(__name__)


def _ref(job: Job) -> PostRefPayload:
    ref = PostRefPayload.from_dict(job.payload)
    if not ref.post_id or not ref.link:
        raise PermanentError(f"{job.type} without a link", reason="bad_payload")
    return ref


class ContentFetchHandler:
    def __init__(self, posts: PostRepository, pipeline: ContentPipeline, queue: JobQueue) -> None:
        self._posts = posts
        self._pipeline = pipeline
        self._queue = queue

    async def __call__(self, job: Job) -> None:
        ref = _ref(job)
        feed_html = await self._posts.get_feed_html(ref.post_id)
        try:
            fetched = await self._pipeline.fetch(ref.link, feed_html)
        except PermanentError as exc:
            await record_summary_failure(self._posts, ref.post_id, str(exc))
            raise

        if not await self._posts.save_content(
            ref.post_id, fetched.plain_text, fetched.thumbnail_url
        ):
            raise PermanentError(f"post not found: {ref.post_id}", reason="post_deleted")
        if fetched.published_at:
            await self._posts.correct_published_at(ref.post_id, fetched.published_at)
        await enqueue_summary_requested(self._queue, ref, priority=job.priority)
        logger.info(
            "content fetched", extra={"post_id": ref.post_id, "chars": len(fetched.plain_text)}
        )


class SummaryRequestedHandler:
    """본문 → 쉽게 읽기(TL;DR·풀어쓴 본문·주제·태그). TL;DR 한 문장이 카드 요약 자리에 들어간다."""

    def __init__(
        self, posts: PostRepository, queue: JobQueue, explainer: ExplainerGenerator
    ) -> None:
        self._posts = posts
        self._queue = queue
        self._explainer = explainer

    async def __call__(self, job: Job) -> None:
        ref = _ref(job)
        plain_text = await self._posts.get_plain_text(ref.post_id)
        if not plain_text:
            # 본문을 아직 못 받았다(나누기 전에 걸린 잡이거나 재생성 요청). 가져오기부터.
            await enqueue_content_fetch(self._queue, ref, priority=job.priority)
            logger.info("no content yet; fetching first", extra={"post_id": ref.post_id})
            return

        try:
            await self._explain(ref, plain_text)
        except QuotaExceededError:
            # 쿼터는 시간이 지나면 풀린다. 사유를 남기지 않는다 —
            # 어드민 화면에 "실패"로 보이면 안 된다.
            raise
        except PermanentError as exc:
            await record_summary_failure(self._posts, ref.post_id, str(exc))
            raise

    async def _explain(self, ref: PostRefPayload, plain_text: str) -> None:
        explainer = await self._explainer.generate(
            ref.post_id, ref.title, ref.blog_name, plain_text
        )
        await self._queue.enqueue(
            JobType.SUMMARY_COMPLETED,
            ref.post_id,
            SummaryCompletedPayload(
                post_id=ref.post_id,
                summary=explainer.tldr.one_liner,
                categories=explainer.categories,
                tags=explainer.tags,
                model_name=explainer.generation.model,
                explainer=explainer.model_dump(mode="json", by_alias=True, exclude={"id"}),
            ).to_dict(),
        )
        logger.info(
            "post explained",
            extra={
                "post_id": ref.post_id,
                "model": explainer.generation.model,
                "chars": len(explainer.body_md),
                "checks_passed": explainer.checks.passed,
            },
        )
