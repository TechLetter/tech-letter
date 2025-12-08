from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...services.posts_service import PostsService, get_posts_service

from ..schemas.posts import (
    ListPostsResponse,
    PostPlainTextResponse,
    PostResponse,
    PostsBatchRequest,
)
from common.models.post import ListPostsFilter


router = APIRouter()


@router.get(
    "",
    response_model=ListPostsResponse,
    summary="포스트 목록 조회",
    description=(
        "카테고리/태그/블로그 기준으로 필터링된 포스트 목록을 "
        "페이지네이션하여 반환한다."
    ),
)
def list_posts(
    page: int = Query(1, ge=1, description="조회할 페이지 (1부터 시작)"),
    page_size: int = Query(
        20,
        ge=1,
        le=100,
        description="페이지당 아이템 개수 (1~100)",
    ),
    categories: List[str] = Query(
        default_factory=list,
        description="필터링할 카테고리 목록 (정확 일치, 대소문자 무시)",
    ),
    tags: List[str] = Query(
        default_factory=list,
        description="필터링할 태그 목록 (정확 일치, 대소문자 무시)",
    ),
    blog_id: Optional[str] = Query(
        default=None,
        description="특정 블로그 ID 로 필터링",
    ),
    blog_name: Optional[str] = Query(
        default=None,
        description="특정 블로그 이름으로 필터링 (정확 일치, 대소문자 무시)",
    ),
    status_ai_summarized: Optional[bool] = Query(
        default=None,
        description="AI 요약 완료 여부 필터링",
    ),
    service: PostsService = Depends(get_posts_service),
) -> ListPostsResponse:
    flt = ListPostsFilter(
        page=page,
        page_size=page_size,
        categories=categories,
        tags=tags,
        blog_id=blog_id,
        blog_name=blog_name,
        status_ai_summarized=status_ai_summarized,
    )
    items, total = service.list_posts(flt)
    dto_items = [PostResponse.from_domain(post) for post in items]
    return ListPostsResponse(total=total, items=dto_items)


@router.get(
    "/{post_id}",
    response_model=PostResponse,
    summary="단일 포스트 조회",
    description="post_id로 포스트를 조회한다.",
)
def get_post(
    post_id: str,
    service: PostsService = Depends(get_posts_service),
) -> PostResponse:
    post = service.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="post not found")
    return PostResponse.from_domain(post)


@router.get(
    "/{post_id}/plain-text",
    response_model=PostPlainTextResponse,
    summary="포스트 plain_text 조회",
    description=(
        "특정 포스트의 plain_text 를 별도로 조회한다. "
        "리스트/기본 조회에서는 plain_text 를 포함하지 않는다."
    ),
)
def get_post_plain_text(
    post_id: str,
    service: PostsService = Depends(get_posts_service),
) -> PostPlainTextResponse:
    result = service.get_plain_text(post_id)
    if result is None:
        raise HTTPException(status_code=404, detail="post not found")

    return PostPlainTextResponse(plain_text=result)


@router.post(
    "/{post_id}/view",
    summary="포스트 조회수 증가",
    description="특정 포스트의 view_count 를 1 증가시킨다.",
)
def increment_post_view(
    post_id: str,
    service: PostsService = Depends(get_posts_service),
) -> dict[str, str]:
    ok = service.increment_view_count(post_id)
    if not ok:
        raise HTTPException(status_code=404, detail="post not found")
    return {"message": "view count incremented"}


@router.post(
    "/batch",
    response_model=ListPostsResponse,
    summary="포스트 일괄 조회",
    description="post_id 목록으로 여러 포스트를 한 번에 조회한다.",
)
def get_posts_batch(
    body: PostsBatchRequest,
    service: PostsService = Depends(get_posts_service),
) -> ListPostsResponse:
    posts = service.list_by_ids(body.ids)
    dto_items = [PostResponse.from_domain(post) for post in posts]
    return ListPostsResponse(total=len(dto_items), items=dto_items)
