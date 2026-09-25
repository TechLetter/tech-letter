"""요약 도메인 잡 핸들러.

`content.fetch_requested` → 원문 확보·저장 → `summary.requested`
`summary.requested` → 저장된 본문으로 요약 → `summary.completed` 발행.
영구 실패면 포스트에 사유를 남긴다 — 어드민이 "왜 요약이 안 됐나"를 본다.
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
    from techletter.summary.pipeline import SummaryPipeline

__all__ = ["ContentFetchHandler", "SummaryRequestedHandler"]

logger = get_logger(__name__)


def _ref(job: Job) -> PostRefPayload:
    ref = PostRefPayload.from_dict(job.payload)
    if not ref.post_id or not ref.link:
        raise PermanentError(f"{job.type} without a link", reason="bad_payload")
    return ref


class ContentFetchHandler:
    def __init__(self, posts: PostRepository, pipeline: SummaryPipeline, queue: JobQueue) -> None:
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
        await enqueue_summary_requested(self._queue, ref, priority=job.priority)
        logger.info(
            "content fetched", extra={"post_id": ref.post_id, "chars": len(fetched.plain_text)}
        )


class SummaryRequestedHandler:
    def __init__(self, posts: PostRepository, pipeline: SummaryPipeline, queue: JobQueue) -> None:
        self._posts = posts
        self._pipeline = pipeline
        self._queue = queue

    async def __call__(self, job: Job) -> None:
        ref = _ref(job)
        plain_text = await self._posts.get_plain_text(ref.post_id)
        if not plain_text:
            # 본문을 아직 못 받았다(나누기 전에 걸린 잡이거나 재요약 요청). 가져오기부터.
            await enqueue_content_fetch(self._queue, ref, priority=job.priority)
            logger.info("no content yet; fetching first", extra={"post_id": ref.post_id})
            return

        try:
            outcome = await self._pipeline.summarize(plain_text)
        except QuotaExceededError:
            # 쿼터는 시간이 지나면 풀린다. 사유를 남기지 않는다 —
            # 어드민 화면에 "실패"로 보이면 안 된다.
            raise
        except PermanentError as exc:
            await record_summary_failure(self._posts, ref.post_id, str(exc))
            raise

        await self._queue.enqueue(
            JobType.SUMMARY_COMPLETED,
            ref.post_id,
            SummaryCompletedPayload(
                post_id=ref.post_id,
                summary=outcome.summary,
                categories=outcome.categories,
                tags=outcome.tags,
                model_name=outcome.model_name,
            ).to_dict(),
        )
        logger.info(
            "post summarized",
            extra={"post_id": ref.post_id, "model": outcome.model_name},
        )
