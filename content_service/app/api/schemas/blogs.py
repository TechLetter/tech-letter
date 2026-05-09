from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl

from common.models.blog import Blog, BlogType
from common.types.datetime import UtcDateTime


class BlogResponse(BaseModel):
    """블로그 응답 DTO."""

    id: str | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    name: str
    url: str
    rss_url: str
    blog_type: BlogType
    is_active: bool
    last_fetched_at: UtcDateTime | None = None
    last_fetch_error: str | None = None
    post_count: int = 0

    @classmethod
    def from_domain(cls, blog: Blog) -> "BlogResponse":
        return cls.model_validate(blog.model_dump())


class BlogMutationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl
    rss_url: HttpUrl
    blog_type: BlogType = "company"
    is_active: bool = True


class DeleteBlogResponse(BaseModel):
    ok: bool
    deleted_posts: int


# ListBlogsResponse 대신 common.schemas.pagination.PaginatedResponse[BlogResponse] 사용
