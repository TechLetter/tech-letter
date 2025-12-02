from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .utils import normalize_id_fields_to_str


class Blog(BaseModel):
    """기술 블로그 소스 도메인 모델.

    Go `models.Blog` 와 동일한 구조를 유지한다.
    """

    id: str | None = Field(default=None, alias="id")
    created_at: datetime = Field(alias="created_at")
    updated_at: datetime = Field(alias="updated_at")
    name: str
    url: str
    rss_url: str = Field(alias="rss_url")
    blog_type: str = Field(alias="blog_type")

    @model_validator(mode="before")
    @classmethod
    def _normalize_object_ids(cls, data: Any) -> Any:
        return normalize_id_fields_to_str(data, fields=["id"])


class ListBlogsFilter(BaseModel):
    """블로그 리스트 조회 옵션.

    현재는 페이지네이션 정보만 필요하며, Go `ListBlogsOptions` 와 동일하다.
    """

    page: int = 1
    page_size: int = 20
