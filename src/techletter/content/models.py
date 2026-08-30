"""content 도메인 문서 모델.

**DB 필드명은 운영 데이터와 정확히 같아야 한다.** `aisummary`, `status.ai_summarized`처럼
규약을 어기는 이름도 유지하고, DTO에서만 `ai_summary`/`status.summarized`로 바꾼다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import Field

from techletter.core.db.documents import BaseDocument, MongoDateTime, PyObjectId, SubDocument

__all__ = [
    "AISummary",
    "Blog",
    "BlogType",
    "EmbeddingMeta",
    "ListPostsFilter",
    "Post",
    "StatusFlags",
]

BlogType = Literal["company", "creator"]


class StatusFlags(SubDocument):
    """`posts.status`. 필드명은 DB 그대로 둔다."""

    ai_summarized: bool = False
    embedded: bool = False
    failed_reason: str | None = None
    """요약이 영구 실패한 사유. 기존 문서에는 없어도 무해."""


class AISummary(SubDocument):
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary: str | None = None
    model_name: str | None = None
    generated_at: MongoDateTime | None = None


class EmbeddingMeta(SubDocument):
    model_name: str
    collection_name: str
    vector_dimension: int
    chunk_count: int = 0
    embedded_at: MongoDateTime | None = None


class Post(BaseDocument):
    blog_id: PyObjectId | None = None
    blog_name: str = ""
    title: str = ""
    link: str = ""
    published_at: MongoDateTime | None = None
    thumbnail_url: str | None = None
    view_count: int = 0
    status: StatusFlags = Field(default_factory=StatusFlags)
    aisummary: AISummary | None = None
    plain_text: str | None = None
    embedding: EmbeddingMeta | None = None


class Blog(BaseDocument):
    name: str = ""
    url: str = ""
    rss_url: str = ""
    blog_type: BlogType = "company"
    is_active: bool = True
    last_fetched_at: MongoDateTime | None = None
    last_fetch_error: str | None = None
    consecutive_failures: int = 0
    """연속 실패 횟수. 임계치를 넘으면 자동 비활성화한다."""
    tls_insecure: bool = False
    """이 블로그만 TLS 검증을 건너뛴다. 기본은 검증한다."""


@dataclass(slots=True)
class ListPostsFilter:
    """포스트 목록 조회 조건.

    주의: `categories`와 `tags`를 함께 주면 **합집합(OR)** 이다 — 프론트의
    필터 UI가 그것을 전제로 만들어져 있다.
    """

    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    blog_id: str | None = None
    published_from: MongoDateTime | None = None
    published_to: MongoDateTime | None = None
    summarized: bool | None = None
    embedded: bool | None = None
    search: str | None = None
