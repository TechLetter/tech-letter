"""content 도메인의 잡 페이로드와 enqueue 헬퍼.

페이로드를 dataclass로 고정해 둔다. 현행은 Kafka 이벤트 dict를 그대로
넘겨서 필드 이름이 바뀔 때마다 조용히 깨졌다.

`key`는 잡 중복 억제의 기준이라 잡 종류마다 유일해야 한다. post_id를 쓴다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from techletter.core.jobs.types import JobType

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.models import Post
    from techletter.core.jobs.queue import JobQueue

__all__ = [
    "EmbeddingCompletedPayload",
    "EmbeddingDeletePayload",
    "EmbeddingRequestedPayload",
    "SummaryCompletedPayload",
    "SummaryRequestedPayload",
    "enqueue_embedding_delete",
    "enqueue_embedding_requested",
    "enqueue_summary_requested",
]


@dataclass(slots=True)
class SummaryRequestedPayload:
    post_id: str
    title: str
    link: str
    blog_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SummaryRequestedPayload:
        return cls(
            post_id=str(data.get("post_id") or ""),
            title=str(data.get("title") or ""),
            link=str(data.get("link") or ""),
            blog_name=str(data.get("blog_name") or ""),
        )


@dataclass(slots=True)
class SummaryCompletedPayload:
    """요약 워커가 만든 결과. 본문(`plain_text`)까지 담는다.

    페이로드가 커지지만(수십 KB) Mongo 문서 한도(16MB)에는 한참 못 미치고,
    Kafka 시절처럼 메시지 크기 제한을 신경 쓸 필요가 없다.
    """

    post_id: str
    summary: str
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    model_name: str = ""
    plain_text: str = ""
    thumbnail_url: str = ""

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
            plain_text=str(data.get("plain_text") or ""),
            thumbnail_url=str(data.get("thumbnail_url") or ""),
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


async def enqueue_summary_requested(
    queue: JobQueue, post: Post, *, trace_id: str | None = None
) -> None:
    if post.id is None:
        return
    payload = SummaryRequestedPayload(
        post_id=str(post.id), title=post.title, link=post.link, blog_name=post.blog_name
    )
    await queue.enqueue(
        JobType.SUMMARY_REQUESTED, str(post.id), payload.to_dict(), trace_id=trace_id
    )


async def enqueue_embedding_requested(
    queue: JobQueue, post_id: str, *, trace_id: str | None = None
) -> None:
    await queue.enqueue(
        JobType.EMBEDDING_REQUESTED,
        post_id,
        EmbeddingRequestedPayload(post_id=post_id).to_dict(),
        trace_id=trace_id,
    )


async def enqueue_embedding_delete(
    queue: JobQueue, post_ids: list[str], *, key: str, trace_id: str | None = None
) -> None:
    """벡터 삭제를 요청한다. 포스트/블로그 삭제 뒤에 부른다.

    삭제는 여러 건을 한 잡에 묶는다. 블로그를 지우면 포스트가 수백 개라
    잡을 하나씩 만들면 큐가 그것으로 가득 찬다.
    """
    if not post_ids:
        return
    await queue.enqueue(
        JobType.EMBEDDING_DELETE_REQUESTED,
        key,
        EmbeddingDeletePayload(post_ids=post_ids).to_dict(),
        trace_id=trace_id,
        dedupe=False,
    )
