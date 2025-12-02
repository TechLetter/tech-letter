from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..types.datetime import UtcDateTime
from ..types.objectid import ObjectIdStr
from .utils import normalize_id_fields_to_str


class StatusFlags(BaseModel):
    """포스트 상태 플래그.

    Go `models.StatusFlags` 와 동일한 구조를 유지한다.
    """

    ai_summarized: bool = Field(default=False, alias="ai_summarized")


class AISummary(BaseModel):
    """AI 요약 결과.

    Go `models.AISummary` 와 동일한 필드를 가진다.
    """

    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    model_name: str = Field(default="", alias="model_name")
    generated_at: UtcDateTime = Field(alias="generated_at")


class Post(BaseModel):
    """게시글 도메인 모델 (API/이벤트/저장소에서 공통 사용).

    - Go `models.Post` 의 bson/json 태그와 동일한 필드 이름을 사용한다.
    - MongoDB `_id` 는 id(str) 로 노출하며, 저장소 레이어에서 ObjectId 로 변환한다.
    """

    id: ObjectIdStr | None = Field(default=None, alias="id")
    created_at: UtcDateTime = Field(alias="created_at")
    updated_at: UtcDateTime = Field(alias="updated_at")
    status: StatusFlags = Field(default_factory=StatusFlags)
    view_count: int = Field(default=0, alias="view_count")
    blog_id: ObjectIdStr = Field(alias="blog_id")
    blog_name: str = Field(alias="blog_name")
    title: str
    link: str
    published_at: UtcDateTime = Field(alias="published_at")
    thumbnail_url: str = Field(default="", alias="thumbnail_url")
    rendered_html: str = Field(default="", alias="rendered_html")
    aisummary: AISummary


class ListPostsFilter(BaseModel):
    """포스트 리스트 조회 옵션.

    Go `repositories.ListPostsOptions` 와 1:1 로 매핑되는 필터 구조다.
    """

    page: int = 1
    page_size: int = 20
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    blog_id: str | None = None
    blog_name: str | None = None
