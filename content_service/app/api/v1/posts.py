from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.services.posts_service import PostsService, get_posts_service
from common.models.post import ListPostsFilter, Post


router = APIRouter()


class ListPostsResponse(BaseModel):
    total: int
    items: list[Post]


@router.get("", response_model=ListPostsResponse)
def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    categories: List[str] = Query(default_factory=list),
    tags: List[str] = Query(default_factory=list),
    blog_id: Optional[str] = Query(default=None),
    blog_name: Optional[str] = Query(default=None),
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
    return ListPostsResponse(total=total, items=items)
