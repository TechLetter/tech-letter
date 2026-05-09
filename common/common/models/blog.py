from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

BlogType = Literal["company", "creator"]


class Blog(BaseModel):
    """기술 블로그 소스 도메인 모델"""

    id: str | None = Field(default=None, alias="id")
    created_at: datetime = Field(alias="created_at")
    updated_at: datetime = Field(alias="updated_at")
    name: str
    url: str
    rss_url: str = Field(alias="rss_url")
    blog_type: BlogType = Field(alias="blog_type")
    is_active: bool = Field(default=True, alias="is_active")
    last_fetched_at: datetime | None = Field(default=None, alias="last_fetched_at")
    last_fetch_error: str | None = Field(default=None, alias="last_fetch_error")
    post_count: int = Field(default=0, alias="post_count")


class ListBlogsFilter(BaseModel):
    """블로그 리스트 조회 옵션"""

    page: int = 1
    page_size: int = 20
    include_inactive: bool = False
