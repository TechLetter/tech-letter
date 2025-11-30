from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from common.models.post import AISummary, Post, StatusFlags


class PostResponse(BaseModel):
    """포스트 응답 DTO.

    도메인 모델(Post)을 그대로 노출하지 않고, API 경계를 위한 전용 응답 모델을 사용한다.
    """

    id: str | None
    created_at: datetime
    updated_at: datetime
    status: StatusFlags
    view_count: int
    blog_id: str
    blog_name: str
    title: str
    link: str
    published_at: datetime
    thumbnail_url: str
    rendered_html: str
    aisummary: AISummary

    @classmethod
    def from_domain(cls, post: Post) -> "PostResponse":
        """도메인 Post 모델을 응답 DTO 로 변환한다."""

        return cls.model_validate(post.model_dump())


class ListPostsResponse(BaseModel):
    total: int
    items: list[PostResponse]
