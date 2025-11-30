from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.services.blogs_service import BlogsService, get_blogs_service
from common.models.blog import Blog, ListBlogsFilter


router = APIRouter()


class ListBlogsResponse(BaseModel):
    total: int
    items: list[Blog]


@router.get("", response_model=ListBlogsResponse)
def list_blogs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: BlogsService = Depends(get_blogs_service),
) -> ListBlogsResponse:
    flt = ListBlogsFilter(page=page, page_size=page_size)
    items, total = service.list_blogs(flt)
    return ListBlogsResponse(total=total, items=items)
