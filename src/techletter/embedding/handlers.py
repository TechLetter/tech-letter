"""임베딩 잡 핸들러.

`embedding.requested` → 벡터 생성 + Qdrant 저장 → `embedding.completed` 발행.
메타데이터를 posts에 쓰는 것은 content 도메인의 몫이다(잡 하나가 두 저장소를
동시에 책임지지 않게).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.content.jobs import EmbeddingDeletePayload, EmbeddingRequestedPayload
from techletter.core.errors import PermanentError
from techletter.core.jobs.types import JobType
from techletter.core.logging import get_logger
from techletter.core.time import to_iso_z

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.repositories import PostRepository
    from techletter.core.db.qdrant import VectorStore
    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue
    from techletter.embedding.pipeline import EmbeddingPipeline

__all__ = ["EmbeddingDeleteHandler", "EmbeddingRequestedHandler"]

logger = get_logger(__name__)


class EmbeddingRequestedHandler:
    def __init__(
        self,
        posts: PostRepository,
        pipeline: EmbeddingPipeline,
        store: VectorStore,
        queue: JobQueue,
    ) -> None:
        self._posts = posts
        self._pipeline = pipeline
        self._store = store
        self._queue = queue

    async def __call__(self, job: Job) -> None:
        payload = EmbeddingRequestedPayload.from_dict(job.payload)
        if not payload.post_id:
            raise PermanentError("embedding.requested without post_id", reason="bad_payload")

        post = await self._posts.get(payload.post_id)
        if post is None:
            raise PermanentError(f"post not found: {payload.post_id}", reason="post_deleted")

        body = await self._posts.get_plain_text(payload.post_id)
        summary = post.aisummary.summary if post.aisummary else ""
        # 본문이 없으면 요약이라도 넣는다. 제목만 있는 포스트보다는 낫다.
        text = body or summary or ""

        result = await self._pipeline.run(text)
        await self._store.upsert_chunks(
            post_id=payload.post_id,
            model_name=result.model_name,
            chunks=result.chunks,
            payload={
                "title": post.title,
                "blog_name": post.blog_name,
                "link": post.link,
                "published_at": to_iso_z(post.published_at),
                "categories": post.aisummary.categories if post.aisummary else [],
                "tags": post.aisummary.tags if post.aisummary else [],
            },
        )

        await self._queue.enqueue(
            JobType.EMBEDDING_COMPLETED,
            payload.post_id,
            {
                "post_id": payload.post_id,
                "model_name": result.model_name,
                "collection_name": self._store.collection_for(
                    result.model_name, result.vector_dimension
                ),
                "vector_dimension": result.vector_dimension,
                "chunk_count": len(result.chunks),
            },
            trace_id=job.trace_id,
        )
        logger.info(
            "post embedded",
            extra={"post_id": payload.post_id, "chunks": len(result.chunks)},
        )


class EmbeddingDeleteHandler:
    """포스트가 지워졌을 때 벡터를 정리한다.

    문서와 벡터가 다른 저장소에 있어 같이 지워지지 않는다. 남으면 지워진
    포스트가 검색 결과에 계속 나온다.
    """

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    async def __call__(self, job: Job) -> None:
        payload = EmbeddingDeletePayload.from_dict(job.payload)
        if not payload.post_ids:
            return
        collections = await self._store.delete_posts(payload.post_ids)
        logger.info(
            "vectors deleted",
            extra={"posts": len(payload.post_ids), "collections": collections},
        )
