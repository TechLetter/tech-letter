from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..types.datetime import UtcDateTime
from ..types.objectid import ObjectIdStr
from .utils import normalize_id_fields_to_str


class Blog(BaseModel):
    """기술 블로그 소스 도메인 모델.

    Go `models.Blog` 와 동일한 구조를 유지한다.
    """

    id: ObjectIdStr | None = Field(default=None, alias="id")
    created_at: UtcDateTime = Field(alias="created_at")
    updated_at: UtcDateTime = Field(alias="updated_at")
    name: str
    url: str
    rss_url: str = Field(alias="rss_url")
    blog_type: str = Field(alias="blog_type")


class ListBlogsFilter(BaseModel):
    """블로그 리스트 조회 옵션.

    현재는 페이지네이션 정보만 필요하며, Go `ListBlogsOptions` 와 동일하다.
    """

    page: int = 1
    page_size: int = 20
