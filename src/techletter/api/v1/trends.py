"""트렌드 (04 §4.1, §3.7)."""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import Ctx, MaybeUser
from techletter.api.schemas import Paged, PostOut, RisingTagsOut, TrendSeriesOut
from techletter.api.schemas.query import ListQ, StrQ, clean_list, parse_page
from techletter.api.v1.posts import _bookmarked_ids
from techletter.core.pagination import lenient_int

router = APIRouter(prefix="/trends", tags=["trends"])

DEFAULT_PERIOD = "30d"
DEFAULT_INTERVAL = "week"
DEFAULT_LIMIT = 10
MAX_LIMIT = 50


@router.get("/rising", response_model=RisingTagsOut)
async def rising_tags(
    ctx: Ctx,
    period: str = DEFAULT_PERIOD,
    limit: StrQ = None,
) -> RisingTagsOut:
    parsed = lenient_int(limit, default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT)
    return RisingTagsOut.of(await ctx.trends.rising_tags(period or DEFAULT_PERIOD, parsed))


@router.get("/series", response_model=TrendSeriesOut)
async def tag_series(
    ctx: Ctx,
    tags: ListQ = None,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
) -> TrendSeriesOut:
    return TrendSeriesOut.of(
        await ctx.trends.tag_series(
            clean_list(tags), period or DEFAULT_PERIOD, interval or DEFAULT_INTERVAL
        )
    )


@router.get("/posts", response_model=Paged[PostOut])
async def trend_posts(
    ctx: Ctx,
    user: MaybeUser,
    tags: ListQ = None,
    period: str = DEFAULT_PERIOD,
    page: StrQ = None,
    page_size: StrQ = None,
) -> Paged[PostOut]:
    paging = parse_page(page, page_size)
    found, total = await ctx.trends.list_posts(clean_list(tags), period or DEFAULT_PERIOD, paging)
    marked = await _bookmarked_ids(ctx, user, [str(p.id) for p in found])
    return Paged.of_page(
        [PostOut.of(post, bookmarked=str(post.id) in marked) for post in found], total, paging
    )
