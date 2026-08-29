"""요약 잡 핸들러.

`summary.requested` → 파이프라인 → `summary.completed` 발행.
영구 실패면 포스트에 사유를 남긴다 — 어드민이 "왜 요약이 안 됐나"를 본다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.content.handlers import record_summary_failure
from techletter.content.jobs import SummaryCompletedPayload, SummaryRequestedPayload
from techletter.core.errors import PermanentError, QuotaExceededError
from techletter.core.jobs.types import JobType
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.repositories import PostRepository
    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue
    from techletter.summary.pipeline import SummaryPipeline

__all__ = ["SummaryRequestedHandler"]

logger = get_logger(__name__)


class SummaryRequestedHandler:
    def __init__(self, posts: PostRepository, pipeline: SummaryPipeline, queue: JobQueue) -> None:
        self._posts = posts
        self._pipeline = pipeline
        self._queue = queue

    async def __call__(self, job: Job) -> None:
        payload = SummaryRequestedPayload.from_dict(job.payload)
        if not payload.post_id or not payload.link:
            raise PermanentError("summary.requested without a link", reason="bad_payload")

        try:
            outcome = await self._pipeline.run(payload.link)
        except QuotaExceededError:
            # 쿼터는 시간이 지나면 풀린다. 사유를 남기지 않는다 —
            # 어드민 화면에 "실패"로 보이면 안 된다.
            raise
        except PermanentError as exc:
            await record_summary_failure(self._posts, payload.post_id, str(exc))
            raise

        await self._queue.enqueue(
            JobType.SUMMARY_COMPLETED,
            payload.post_id,
            SummaryCompletedPayload(
                post_id=payload.post_id,
                summary=outcome.summary,
                categories=outcome.categories,
                tags=outcome.tags,
                model_name=outcome.model_name,
                plain_text=outcome.plain_text,
                thumbnail_url=outcome.thumbnail_url,
            ).to_dict(),
            trace_id=job.trace_id,
        )
        logger.info(
            "post summarized",
            extra={"post_id": payload.post_id, "model": outcome.model_name},
        )
