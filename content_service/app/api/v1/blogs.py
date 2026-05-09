from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..schemas.blogs import BlogMutationRequest, BlogResponse, DeleteBlogResponse
from ...services.blogs_service import (
    BlogNotFoundError,
    BlogsService,
    DuplicateBlogError,
    InvalidBlogTypeError,
    get_blogs_service,
)
from common.models.blog import ListBlogsFilter


router = APIRouter()


from common.schemas.pagination import PaginatedResponse


@router.get(
    "",
    response_model=PaginatedResponse[BlogResponse],
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
    include_inactive: bool = Query(
        False,
        description="비활성 블로그까지 포함할지 여부",
    ),
    service: BlogsService = Depends(get_blogs_service),
) -> PaginatedResponse[BlogResponse]:
    flt = ListBlogsFilter(
        page=page,
        page_size=page_size,
        include_inactive=include_inactive,
    )
    items, total = service.list_blogs(flt)
    dto_items = [BlogResponse.from_domain(blog) for blog in items]
    return PaginatedResponse(
        total=total, items=dto_items, page=page, page_size=page_size
    )


@router.post(
    "",
    response_model=BlogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="블로그 소스 생성",
    description="수집 대상 기술 블로그 소스를 생성한다.",
)
def create_blog(
    body: BlogMutationRequest,
    service: BlogsService = Depends(get_blogs_service),
) -> BlogResponse:
    try:
        blog = service.create_blog(
            name=body.name,
            url=str(body.url),
            rss_url=str(body.rss_url),
            blog_type=body.blog_type,
            is_active=body.is_active,
        )
    except DuplicateBlogError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except InvalidBlogTypeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return BlogResponse.from_domain(blog)


@router.put(
    "/{blog_id}",
    response_model=BlogResponse,
    summary="블로그 소스 수정",
    description="수집 대상 기술 블로그 소스를 수정한다.",
)
def update_blog(
    blog_id: str,
    body: BlogMutationRequest,
    service: BlogsService = Depends(get_blogs_service),
) -> BlogResponse:
    try:
        blog = service.update_blog(
            blog_id,
            name=body.name,
            url=str(body.url),
            rss_url=str(body.rss_url),
            blog_type=body.blog_type,
            is_active=body.is_active,
        )
    except BlogNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DuplicateBlogError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except InvalidBlogTypeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return BlogResponse.from_domain(blog)


@router.delete(
    "/{blog_id}",
    response_model=DeleteBlogResponse,
    summary="블로그 소스 삭제",
    description="수집 대상 블로그를 삭제하고, 옵션에 따라 해당 블로그의 포스트도 함께 삭제한다.",
)
def delete_blog(
    blog_id: str,
    delete_posts: bool = Query(
        False,
        description="true이면 해당 블로그의 모든 포스트도 함께 삭제",
    ),
    service: BlogsService = Depends(get_blogs_service),
) -> DeleteBlogResponse:
    try:
        deleted_posts = service.delete_blog(blog_id, delete_posts=delete_posts)
    except BlogNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return DeleteBlogResponse(ok=True, deleted_posts=deleted_posts)
