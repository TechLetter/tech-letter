from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.api.schemas.posts import ListPostsResponse, PostResponse
from app.services.posts_service import PostsService, get_posts_service
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
    service: PostsService = Depends(get_posts_service),
) -> ListPostsResponse:
    flt = ListPostsFilter(
        page=page,
        page_size=page_size,
        categories=categories,
        tags=tags,
        blog_id=blog_id,
        blog_name=blog_name,
    )
    items, total = service.list_posts(flt)
    dto_items = [PostResponse.from_domain(post) for post in items]
    return ListPostsResponse(total=total, items=dto_items)
