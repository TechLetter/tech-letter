"""포스트.

공개 API는 **요약이 끝난 포스트만** 준다. `q`가 있으면 하이브리드 검색의
관련도 순으로 준다(`sort`는 무시한다).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from techletter.api.deps import Ctx, MaybeUser
from techletter.api.schemas import Paged, PostOut
from techletter.api.schemas.query import ListQ, StrQ, clean_list, parse_page, published_range
from techletter.content.models import ListPostsFilter
from techletter.search.service import normalize_query

router = APIRouter(prefix="/posts", tags=["posts"])


def _client_ip(request: Request) -> str | None:
    """요청자 IP. Traefik이 붙인 `X-Forwarded-For`의 **마지막** 값을 쓴다.

    앞쪽 값은 클라이언트가 마음대로 넣을 수 있다. 마지막 값은 프록시가 본 실제
    접속 주소다. 프록시 없이 붙으면 소켓 주소.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    last = forwarded.split(",")[-1].strip()
    return last or (request.client.host if request.client else None)


async def _bookmarked_ids(ctx: Ctx, user: MaybeUser, post_ids: list[str]) -> set[str]:
    """익명이면 빈 집합. 로그인했으면 한 번의 질의로 확인한다."""
    if user is None or not post_ids:
        return set()
    return await ctx.bookmarks.filter_bookmarked(user.user_code, post_ids)


@router.get("", response_model=Paged[PostOut])
async def list_posts(
    ctx: Ctx,
    user: MaybeUser,
    request: Request,
    page: StrQ = None,
    page_size: StrQ = None,
    categories: ListQ = None,
    tags: ListQ = None,
    blog_id: StrQ = None,
    published_from: StrQ = None,
    published_to: StrQ = None,
    sort: StrQ = None,
    q: StrQ = None,
) -> Paged[PostOut]:
    paging = parse_page(page, page_size)
    since, until = published_range(published_from, published_to)
    flt = ListPostsFilter(
        categories=clean_list(categories),
        tags=clean_list(tags),
        blog_id=(blog_id or "").strip() or None,
        published_from=since,
        published_to=until,
        summarized=True,
    )
    # 두 글자 미만 검색어는 검색하지 않은 것으로 본다(입력 도중의 한 글자 등).
    if (query := normalize_query(q)) is not None:
        found, total = await ctx.search.search(query, flt, paging, client=_client_ip(request))
    else:
        found, total = await ctx.posts.list_posts(
            flt,
            paging,
            # 모르는 값은 기본(최신순)으로 본다. 다른 쿼리 파라미터도 관대하게 받는다.
            sort="views" if sort == "views" else "latest",
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
