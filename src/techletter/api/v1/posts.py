"""포스트.

공개 API는 **요약이 끝난 포스트만** 준다.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from techletter.api.deps import Ctx, MaybeUser
from techletter.api.schemas import Paged, PostOut
from techletter.api.schemas.query import ListQ, StrQ, clean_list, parse_page, published_range
from techletter.content.models import ListPostsFilter

router = APIRouter(prefix="/posts", tags=["posts"])


async def _bookmarked_ids(ctx: Ctx, user: MaybeUser, post_ids: list[str]) -> set[str]:
    """익명이면 빈 집합. 로그인했으면 한 번의 질의로 확인한다."""
    if user is None or not post_ids:
        return set()
    return await ctx.bookmarks.filter_bookmarked(user.user_code, post_ids)


@router.get("", response_model=Paged[PostOut])
async def list_posts(
    ctx: Ctx,
    user: MaybeUser,
    page: StrQ = None,
    page_size: StrQ = None,
    categories: ListQ = None,
    tags: ListQ = None,
    blog_id: StrQ = None,
    published_from: StrQ = None,
    published_to: StrQ = None,
) -> Paged[PostOut]:
    paging = parse_page(page, page_size)
    since, until = published_range(published_from, published_to)
    found, total = await ctx.posts.list_posts(
        ListPostsFilter(
            categories=clean_list(categories),
            tags=clean_list(tags),
            blog_id=(blog_id or "").strip() or None,
            published_from=since,
            published_to=until,
            summarized=True,
        ),
        paging,
    )
    marked = await _bookmarked_ids(ctx, user, [str(p.id) for p in found])
    return Paged.of_page(
        [PostOut.of(post, bookmarked=str(post.id) in marked) for post in found], total, paging
    )


@router.get("/{post_id}", response_model=PostOut)
async def get_post(ctx: Ctx, user: MaybeUser, post_id: str) -> PostOut:
    post = await ctx.post_service.get(post_id)
    marked = await _bookmarked_ids(ctx, user, [post_id])
    return PostOut.of(post, bookmarked=post_id in marked)


@router.post("/{post_id}/views", status_code=status.HTTP_204_NO_CONTENT)
async def add_view(ctx: Ctx, post_id: str) -> Response:
    """조회수 +1. 본문이 필요 없어 204를 준다."""
    await ctx.post_service.view(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
