"""어휘 색인 잡.

요약이 반영되면(`SummaryCompletedHandler`) 이 잡을 건다. 주제를 재분류한 뒤에도
다시 건다. 어휘 색인은 요약만 있으면 되므로 임베딩을 기다리지 않는다 — 임베딩 쿼터가
밀리면 며칠씩 걸려 그동안 새 글이 검색에 안 나왔다(2026-09-27).
처리는 임베딩 워커가 한다. 실패하면 이 잡만 큐의 재시도 정책대로 다시 돈다.

삭제는 따로 없다. 색인 컬렉션이 벡터와 같은 prefix라 `EmbeddingDeleteHandler`가
함께 지운다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.core.errors import PermanentError
from techletter.core.jobs.models import PRIORITY_NORMAL
from techletter.core.jobs.types import JobType
from techletter.core.logging import get_logger
from techletter.search.lexical import lexical_point

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.repositories import PostRepository
    from techletter.core.db.qdrant import VectorStore
    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue

__all__ = ["LexicalIndexHandler", "enqueue_lexical_index"]

logger = get_logger(__name__)


async def enqueue_lexical_index(
    queue: JobQueue, post_id: str, *, priority: int = PRIORITY_NORMAL
) -> Job | None:
    return await queue.enqueue(
        JobType.LEXICAL_INDEX_REQUESTED, post_id, {"post_id": post_id}, priority=priority
    )


class LexicalIndexHandler:
    def __init__(self, posts: PostRepository, store: VectorStore) -> None:
        self._posts = posts
        self._store = store

    async def __call__(self, job: Job) -> None:
        post_id = str(job.payload.get("post_id") or "")
        if not post_id:
            raise PermanentError("lexical index without post_id", reason="bad_payload")
        post = await self._posts.get(post_id)
        if post is None:
            raise PermanentError(f"post not found: {post_id}", reason="post_deleted")
        if not post.status.ai_summarized:
            # 공개 검색은 요약된 글만 다룬다. 요약이 끝나면 임베딩을 거쳐 다시 온다.
            logger.info("lexical index skipped; not summarized", extra={"post_id": post_id})
            return
        await self._store.upsert_lexical([lexical_point(post)])
        logger.info("post lexically indexed", extra={"post_id": post_id})
