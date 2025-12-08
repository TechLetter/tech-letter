from __future__ import annotations

from pydantic import BaseModel

from common.models.post import AISummary, Post, StatusFlags
from common.types.datetime import UtcDateTime


class PostResponse(BaseModel):
    """포스트 응답 DTO.

    도메인 모델(Post)을 그대로 노출하지 않고, API 경계를 위한 전용 응답 모델을 사용한다.
    """

    id: str | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    status: StatusFlags
    view_count: int
    blog_id: str
    blog_name: str
    title: str
    link: str
    published_at: UtcDateTime
    thumbnail_url: str | None = None
    aisummary: AISummary

    @classmethod
    def from_domain(cls, post: Post) -> "PostResponse":
        """도메인 Post 모델을 응답 DTO 로 변환한다."""

        return cls.model_validate(post.model_dump())


class ListPostsResponse(BaseModel):
    total: int
    items: list[PostResponse]


class PostsBatchRequest(BaseModel):
    """포스트 일괄 조회 요청 DTO."""

    ids: list[str]


class PostPlainTextResponse(BaseModel):
    """포스트 plain_text 전용 DTO."""

    plain_text: str | None = None
