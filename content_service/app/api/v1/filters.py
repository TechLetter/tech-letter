from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query

from app.api.schemas.filters import (
    BlogFilterItem,
    BlogFilterResponse,
    CategoryFilterResponse,
    FilterItem,
    TagFilterResponse,
)
from app.services.filters_service import FiltersService, get_filters_service


router = APIRouter()


@router.get(
    "/categories",
    response_model=CategoryFilterResponse,
    summary="카테고리 필터 목록 조회",
    description="포스트 필터링에 사용할 카테고리 목록과 각 카테고리의 포스트 개수를 반환한다.",
)
def get_category_filters(
    blog_id: str | None = Query(default=None, description="블로그 ID로 필터링"),
    tags: List[str] = Query(
        default_factory=list, description="태그 목록으로 필터링 (OR)"
    ),
    service: FiltersService = Depends(get_filters_service),
) -> CategoryFilterResponse:
    results = service.get_category_filters(blog_id, tags)
    items = [FilterItem(name=name, count=count) for name, count in results]
    return CategoryFilterResponse(items=items)


@router.get(
    "/tags",
    response_model=TagFilterResponse,
    summary="태그 필터 목록 조회",
    description="포스트 필터링에 사용할 태그 목록과 각 태그의 포스트 개수를 반환한다.",
)
def get_tag_filters(
    blog_id: str | None = Query(default=None, description="블로그 ID로 필터링"),
    categories: List[str] = Query(
        default_factory=list, description="카테고리 목록으로 필터링 (OR)"
    ),
    service: FiltersService = Depends(get_filters_service),
) -> TagFilterResponse:
    results = service.get_tag_filters(blog_id, categories)
    items = [FilterItem(name=name, count=count) for name, count in results]
    return TagFilterResponse(items=items)


@router.get(
    "/blogs",
    response_model=BlogFilterResponse,
    summary="블로그 필터 목록 조회",
    description="포스트 필터링에 사용할 블로그 목록과 각 블로그의 포스트 개수를 반환한다.",
)
def get_blog_filters(
    categories: List[str] = Query(
        default_factory=list, description="카테고리 목록으로 필터링 (OR)"
    ),
    tags: List[str] = Query(
        default_factory=list, description="태그 목록으로 필터링 (OR)"
    ),
    service: FiltersService = Depends(get_filters_service),
) -> BlogFilterResponse:
    results = service.get_blog_filters(categories, tags)
    items = [
        BlogFilterItem(id=blog_id, name=blog_name, count=count)
        for blog_id, blog_name, count in results
    ]
    return BlogFilterResponse(items=items)
