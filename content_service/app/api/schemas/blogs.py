from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from common.models.blog import Blog


class BlogResponse(BaseModel):
    """블로그 응답 DTO."""

    id: str | None
    created_at: datetime
    updated_at: datetime
    name: str
    url: str
    rss_url: str
    blog_type: str

    @classmethod
    def from_domain(cls, blog: Blog) -> "BlogResponse":
        return cls.model_validate(blog.model_dump())


class ListBlogsResponse(BaseModel):
    total: int
    items: list[BlogResponse]
