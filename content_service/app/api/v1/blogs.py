from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..schemas.blogs import BlogResponse, ListBlogsResponse
from ...services.blogs_service import BlogsService, get_blogs_service
from common.models.blog import ListBlogsFilter


router = APIRouter()


@router.get(
    "",
    response_model=ListBlogsResponse,
    summary="블로그 소스 목록 조회",
    description="수집 대상 기술 블로그 소스 목록을 페이지네이션하여 반환한다.",
)
def list_blogs(
    page: int = Query(1, ge=1, description="조회할 페이지 (1부터 시작)"),
    page_size: int = Query(
        20,
        ge=1,
        le=100,
        description="페이지당 아이템 개수 (1~100)",
    ),
    service: BlogsService = Depends(get_blogs_service),
) -> ListBlogsResponse:
    flt = ListBlogsFilter(page=page, page_size=page_size)
    items, total = service.list_blogs(flt)
    dto_items = [BlogResponse.from_domain(blog) for blog in items]
    return ListBlogsResponse(total=total, items=dto_items)
