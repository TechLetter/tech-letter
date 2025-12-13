from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Self


class EventType:
    POST_SUMMARY_REQUESTED = "post.summary_requested"
    POST_SUMMARY_RESPONSE = "post.summary_response"
    POST_EMBEDDING_REQUESTED = "post.embedding_requested"
    POST_EMBEDDING_RESPONSE = "post.embedding_response"
    POST_EMBEDDING_APPLIED = "post.embedding_applied"


@dataclass(slots=True)
class PostSummaryRequestedEvent:
    id: str
    type: str
    timestamp: str
    source: str
    version: str
    post_id: str
    title: str
    blog_name: str
    link: str
    published_at: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            post_id=str(data["post_id"]),
            title=str(data["title"]),
            blog_name=str(data["blog_name"]),
            link=str(data["link"]),
            published_at=str(data["published_at"]),
        )


@dataclass(slots=True)
class PostSummaryResponseEvent:
    id: str
    type: str
    timestamp: str
    source: str
    version: str
    post_id: str
    link: str
    categories: list[str]
    tags: list[str]
    summary: str
    model_name: str
    plain_text: str
    thumbnail_url: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            post_id=str(data["post_id"]),
            link=str(data["link"]),
            plain_text=str(data["plain_text"]),
            thumbnail_url=str(data["thumbnail_url"]),
            categories=list(data.get("categories", [])),
            tags=list(data.get("tags", [])),
            summary=str(data["summary"]),
            model_name=str(data["model_name"]),
        )


@dataclass(slots=True)
class PostEmbeddingRequestedEvent:
    """임베딩 생성 요청 이벤트.

    Summary Worker가 요약 완료 후 발행하며, Embedding Worker가 구독한다.
    """

    id: str
    type: str
    timestamp: str
    source: str
    version: str
    post_id: str
    title: str
    blog_name: str
    link: str
    published_at: str
    categories: list[str]
    tags: list[str]
    plain_text: str
    summary: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            post_id=str(data["post_id"]),
            title=str(data["title"]),
            blog_name=str(data["blog_name"]),
            link=str(data["link"]),
            published_at=str(data["published_at"]),
            categories=list(data.get("categories", [])),
            tags=list(data.get("tags", [])),
            plain_text=str(data["plain_text"]),
            summary=str(data["summary"]),
        )


@dataclass(slots=True)
class EmbeddingChunk:
    """임베딩된 청크 정보."""

    chunk_index: int
    chunk_text: str
    vector: list[float]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            chunk_index=int(data["chunk_index"]),
            chunk_text=str(data["chunk_text"]),
            vector=list(data["vector"]),
        )


@dataclass(slots=True)
class PostEmbedResponseEvent:
    """임베딩 생성 완료 응답 이벤트.

    Embedding Worker가 임베딩 생성 후 발행하며, Chatbot Service가 구독하여
    Vector DB(Qdrant)에 upsert한다.
    """

    id: str
    type: str
    timestamp: str
    source: str
    version: str
    post_id: str
    title: str
    blog_name: str
    link: str
    published_at: str
    categories: list[str]
    tags: list[str]
    chunks: list[EmbeddingChunk]
    model_name: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        chunks_data = data.get("chunks", [])
        chunks = [EmbeddingChunk.from_dict(c) for c in chunks_data]
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            post_id=str(data["post_id"]),
            title=str(data["title"]),
            blog_name=str(data["blog_name"]),
            link=str(data["link"]),
            published_at=str(data["published_at"]),
            categories=list(data.get("categories", [])),
            tags=list(data.get("tags", [])),
            chunks=chunks,
            model_name=str(data["model_name"]),
        )


@dataclass(slots=True)
class PostEmbeddingAppliedEvent:
    id: str
    type: str
    timestamp: str
    source: str
    version: str
    post_id: str
    model_name: str
    collection_name: str
    vector_dimension: int
    chunk_count: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            post_id=str(data["post_id"]),
            model_name=str(data["model_name"]),
            collection_name=str(data.get("collection_name", "")),
            vector_dimension=int(data.get("vector_dimension", 0)),
            chunk_count=int(data["chunk_count"]),
        )
