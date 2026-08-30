"""content 도메인의 잡 핸들러.

요약이 끝나면 문서에 반영하고 임베딩을 이어서 요청한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.content.jobs import (
    EmbeddingCompletedPayload,
    SummaryCompletedPayload,
    enqueue_embedding_requested,
)
from techletter.core.errors import PermanentError
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.repositories import PostRepository
    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue

__all__ = ["EmbeddingCompletedHandler", "SummaryCompletedHandler", "record_summary_failure"]

logger = get_logger(__name__)


class SummaryCompletedHandler:
    """`summary.completed` 처리. 요약 결과를 posts에 쓰고 임베딩을 건다."""

    def __init__(self, posts: PostRepository, queue: JobQueue) -> None:
        self._posts = posts
        self._queue = queue

    async def __call__(self, job: Job) -> None:
        payload = SummaryCompletedPayload.from_dict(job.payload)
        if not payload.post_id:
            raise PermanentError("summary.completed without post_id", reason="bad_payload")

        now = utcnow()
        # 점 표기로 하위 필드만 건드린다. `status` 전체를 덮어쓰면 임베딩
        # 워커가 같은 문서에 동시에 쓸 때 서로의 플래그를 지운다.
        updates = {
            "aisummary": {
                "categories": payload.categories,
                "tags": payload.tags,
                "summary": payload.summary,
                "model_name": payload.model_name,
                "generated_at": now,
            },
            "status.ai_summarized": True,
            "status.failed_reason": None,
        }
        if payload.plain_text:
            updates["plain_text"] = payload.plain_text
        if payload.thumbnail_url:
            updates["thumbnail_url"] = payload.thumbnail_url

        if not await self._posts.apply_summary(payload.post_id, updates):
            # 요약하는 동안 포스트가 지워졌다. 재시도해도 의미가 없다.
            raise PermanentError(f"post not found: {payload.post_id}", reason="post_deleted")

        logger.info(
            "summary applied",
            extra={"post_id": payload.post_id, "model": payload.model_name},
        )
        await enqueue_embedding_requested(self._queue, payload.post_id, trace_id=job.trace_id)


class EmbeddingCompletedHandler:
    """`embedding.completed` 처리. 어느 모델·컬렉션에 몇 조각을 넣었는지 남긴다."""

    def __init__(self, posts: PostRepository) -> None:
        self._posts = posts

    async def __call__(self, job: Job) -> None:
        payload = EmbeddingCompletedPayload.from_dict(job.payload)
        if not payload.post_id:
            raise PermanentError("embedding.completed without post_id", reason="bad_payload")

        applied = await self._posts.apply_embedding_meta(
            payload.post_id,
            {
                "model_name": payload.model_name,
                "collection_name": payload.collection_name,
                "vector_dimension": payload.vector_dimension,
                "chunk_count": payload.chunk_count,
            },
            embedded_at=utcnow(),
        )
        if not applied:
            raise PermanentError(f"post not found: {payload.post_id}", reason="post_deleted")
        logger.info(
            "embedding applied",
            extra={"post_id": payload.post_id, "chunks": payload.chunk_count},
        )


async def record_summary_failure(posts: PostRepository, post_id: str, reason: str) -> None:
    """요약이 영구 실패했을 때 사유를 문서에 남긴다.

    잡은 `dead`로 가지만 포스트 쪽에도 흔적이 있어야 어드민 목록에서 바로 보인다.
    """
    if post_id:
        await posts.mark_summary_failed(post_id, reason)
