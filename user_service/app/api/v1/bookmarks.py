from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..schemas.bookmarks import (
    BookmarkCheckRequest,
    BookmarkCheckResponse,
    BookmarkCreateRequest,
    BookmarkItem,
    ListBookmarksResponse,
)
from ...services.bookmarks_service import BookmarksService, get_bookmarks_service


router = APIRouter()


@router.post(
    "",
    response_model=BookmarkItem,
    summary="유저 북마크 추가",
)
async def add_bookmark(
    body: BookmarkCreateRequest,
    service: BookmarksService = Depends(get_bookmarks_service),
) -> BookmarkItem:
    bookmark = service.add_bookmark(user_code=body.user_code, post_id=body.post_id)
    return BookmarkItem(post_id=bookmark.post_id, created_at=bookmark.created_at)


@router.delete(
    "",
    summary="유저 북마크 삭제",
)
async def remove_bookmark(
    body: BookmarkCreateRequest,
    service: BookmarksService = Depends(get_bookmarks_service),
) -> dict[str, str]:
    deleted = service.remove_bookmark(user_code=body.user_code, post_id=body.post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="bookmark not found")
    return {"message": "bookmark_deleted"}


@router.get(
    "",
    response_model=ListBookmarksResponse,
    summary="유저 북마크 목록 조회",
)
async def list_bookmarks(
    user_code: str = Query(..., description="유저 코드"),
    page: int = Query(1, ge=1, description="조회할 페이지 (1부터 시작)"),
    page_size: int = Query(
        20,
        ge=1,
        le=100,
        description="페이지당 아이템 개수 (1~100)",
    ),
    service: BookmarksService = Depends(get_bookmarks_service),
) -> ListBookmarksResponse:
    items, total = service.list_bookmarks(
        user_code=user_code, page=page, page_size=page_size
    )
    dto_items = [
        BookmarkItem(post_id=b.post_id, created_at=b.created_at) for b in items
    ]
    return ListBookmarksResponse(total=total, items=dto_items)


@router.post(
    "/check",
    response_model=BookmarkCheckResponse,
    summary="유저 북마크 여부 일괄 조회",
)
async def check_bookmarks(
    body: BookmarkCheckRequest,
    service: BookmarksService = Depends(get_bookmarks_service),
) -> BookmarkCheckResponse:
    bookmarked_ids = service.get_bookmarked_post_ids(
        user_code=body.user_code, post_ids=body.post_ids
    )
    return BookmarkCheckResponse(bookmarked_post_ids=bookmarked_ids)
