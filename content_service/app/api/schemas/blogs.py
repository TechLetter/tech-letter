from __future__ import annotations

from pydantic import BaseModel

from common.models.blog import Blog
from common.types.datetime import UtcDateTime


class BlogResponse(BaseModel):
    """블로그 응답 DTO."""

    id: str | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    name: str
    url: str
    rss_url: str
    blog_type: str

    @classmethod
    def from_domain(cls, blog: Blog) -> "BlogResponse":
        return cls.model_validate(blog.model_dump())


# ListBlogsResponse 대신 common.schemas.pagination.PaginatedResponse[BlogResponse] 사용
