"""북마크 (04 §4.1).

현행은 `/posts/{id}/bookmark`이라 `/posts/bookmarks`가 `/posts/{id}`와
충돌했다. 독립 리소스로 옮겨 그 원인을 없앴다.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from techletter.api.deps import Ctx, CurrentUser
from techletter.api.schemas import BookmarkIn, BookmarkOut, Paged, PostOut
from techletter.api.schemas.query import StrQ, parse_page
from techletter.core.errors import ResourceNotFoundError
from techletter.core.time import to_iso_z

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


@router.get("", response_model=Paged[PostOut])
async def list_bookmarks(
    ctx: Ctx,
    user: CurrentUser,
    page: StrQ = None,
    page_size: StrQ = None,
) -> Paged[PostOut]:
    paging = parse_page(page, page_size)
    post_ids, total = await ctx.bookmarks.list_post_ids(user.user_code, paging)
    posts = await ctx.post_service.get_many(post_ids)
    # 여기 담긴 포스트는 정의상 전부 북마크된 것이다.
    return Paged.of_page([PostOut.of(p, bookmarked=True) for p in posts], total, paging)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BookmarkOut)
async def add_bookmark(ctx: Ctx, user: CurrentUser, body: BookmarkIn) -> BookmarkOut:
    # 없는 포스트를 북마크하면 목록에 유령이 남는다. 먼저 확인한다.
    if await ctx.posts.get(body.post_id) is None:
        raise ResourceNotFoundError(f"post not found: {body.post_id}")
    bookmark = await ctx.bookmarks.add(user.user_code, body.post_id)
    return BookmarkOut(post_id=bookmark.post_id, created_at=to_iso_z(bookmark.created_at))


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bookmark(ctx: Ctx, user: CurrentUser, post_id: str) -> Response:
    if not await ctx.bookmarks.remove(user.user_code, post_id):
        raise ResourceNotFoundError("북마크를 찾을 수 없습니다.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
