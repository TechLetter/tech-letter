"""content 도메인의 잡 페이로드와 enqueue 헬퍼.

페이로드를 dataclass로 고정해 둔다 — 필드 이름이 바뀌면 타입 체크에서 잡힌다.

`key`는 잡 중복 억제의 기준이라 잡 종류마다 유일해야 한다. post_id를 쓴다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from techletter.core.jobs.models import PRIORITY_NORMAL
from techletter.core.jobs.types import JobType

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.models import Post
    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue

__all__ = [
    "EmbeddingCompletedPayload",
    "EmbeddingDeletePayload",
    "EmbeddingRequestedPayload",
    "PostRefPayload",
    "SummaryCompletedPayload",
    "enqueue_content_fetch",
    "enqueue_embedding_delete",
    "enqueue_embedding_requested",
    "enqueue_summary_requested",
]


@dataclass(slots=True)
class PostRefPayload:
    """`content.fetch_requested`와 `summary.requested`가 같이 쓰는 글 참조."""

    post_id: str
    title: str
    link: str
    blog_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def of(cls, post: Post) -> PostRefPayload:
        return cls(post_id=str(post.id), title=post.title, link=post.link, blog_name=post.blog_name)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PostRefPayload:
        return cls(
            post_id=str(data.get("post_id") or ""),
            title=str(data.get("title") or ""),
            link=str(data.get("link") or ""),
            blog_name=str(data.get("blog_name") or ""),
        )


@dataclass(slots=True)
class SummaryCompletedPayload:
    """요약 결과. 본문·썸네일은 가져오기 단계가 이미 글에 저장했다."""

    post_id: str
    summary: str
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    model_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SummaryCompletedPayload:
        return cls(
            post_id=str(data.get("post_id") or ""),
            summary=str(data.get("summary") or ""),
            categories=[str(c) for c in (data.get("categories") or [])],
            tags=[str(t) for t in (data.get("tags") or [])],
            model_name=str(data.get("model_name") or ""),
        )


@dataclass(slots=True)
class EmbeddingRequestedPayload:
    post_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingRequestedPayload:
        return cls(post_id=str(data.get("post_id") or ""))


@dataclass(slots=True)
class EmbeddingCompletedPayload:
    """임베딩 워커가 벡터를 다 넣은 뒤 남기는 메타데이터."""

    post_id: str
    model_name: str
    collection_name: str
    vector_dimension: int
    chunk_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingCompletedPayload:
        return cls(
            post_id=str(data.get("post_id") or ""),
            model_name=str(data.get("model_name") or ""),
            collection_name=str(data.get("collection_name") or ""),
            vector_dimension=int(data.get("vector_dimension") or 0),
            chunk_count=int(data.get("chunk_count") or 0),
        )


@dataclass(slots=True)
class EmbeddingDeletePayload:
    post_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingDeletePayload:
        return cls(post_ids=[str(p) for p in (data.get("post_ids") or [])])


async def enqueue_content_fetch(
    queue: JobQueue,
    ref: PostRefPayload,
    *,
    priority: int = PRIORITY_NORMAL,
) -> Job | None:
    """원문 가져오기를 건다. 새 글의 첫 단계다. 이미 대기 중이면 None(중복 억제)."""
    if not ref.post_id:
        return None
    return await queue.enqueue(
        JobType.CONTENT_FETCH_REQUESTED, ref.post_id, ref.to_dict(), priority=priority
    )


async def enqueue_summary_requested(
    queue: JobQueue,
    ref: PostRefPayload,
    *,
    priority: int = PRIORITY_NORMAL,
) -> Job | None:
    """저장된 본문으로 요약을 건다. 이미 대기 중이면 None(중복 억제).

    `priority`는 백필 호출자가 `PRIORITY_BACKFILL`을 넘긴다 — 신규 수집
    포스트가 항상 먼저 처리되게 하기 위해서다.
    """
    if not ref.post_id:
        return None
    return await queue.enqueue(
        JobType.SUMMARY_REQUESTED, ref.post_id, ref.to_dict(), priority=priority
    )


async def enqueue_embedding_requested(
    queue: JobQueue,
    post_id: str,
    *,
    priority: int = PRIORITY_NORMAL,
) -> Job | None:
    return await queue.enqueue(
        JobType.EMBEDDING_REQUESTED,
        post_id,
        EmbeddingRequestedPayload(post_id=post_id).to_dict(),
        priority=priority,
    )


async def enqueue_embedding_delete(queue: JobQueue, post_ids: list[str], *, key: str) -> Job | None:
    """벡터 삭제를 요청한다. 포스트/블로그 삭제 뒤에 부른다.

    삭제는 여러 건을 한 잡에 묶는다. 블로그를 지우면 포스트가 수백 개라
    잡을 하나씩 만들면 큐가 그것으로 가득 찬다.
    """
    if not post_ids:
        return None
    return await queue.enqueue(
        JobType.EMBEDDING_DELETE_REQUESTED,
        key,
        EmbeddingDeletePayload(post_ids=post_ids).to_dict(),
        dedupe=False,
    )
