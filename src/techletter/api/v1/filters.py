"""필터 통계 (04 §4.1).

세 경로를 유지한다 — 프론트가 독립적으로 호출하고 독립적으로 캐시한다.
페이지 개념이 없어 `{items, total}` 봉투를 쓴다(04 §1.2).
"""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import Ctx
from techletter.api.schemas import BlogFilterOut, FilterOut, Listing
from techletter.api.schemas.query import ListQ, StrQ, clean_list

router = APIRouter(prefix="/filters", tags=["filters"])


@router.get("/categories", response_model=Listing[FilterOut])
async def category_filters(
    ctx: Ctx,
    blog_id: StrQ = None,
    tags: ListQ = None,
) -> Listing[FilterOut]:
    items = await ctx.filters.categories((blog_id or "").strip() or None, clean_list(tags))
    return Listing.of([FilterOut.of(item) for item in items])


@router.get("/tags", response_model=Listing[FilterOut])
async def tag_filters(
    ctx: Ctx,
    blog_id: StrQ = None,
    categories: ListQ = None,
) -> Listing[FilterOut]:
    items = await ctx.filters.tags((blog_id or "").strip() or None, clean_list(categories))
    return Listing.of([FilterOut.of(item) for item in items])


@router.get("/blogs", response_model=Listing[BlogFilterOut])
async def blog_filters(
    ctx: Ctx,
    categories: ListQ = None,
    tags: ListQ = None,
) -> Listing[BlogFilterOut]:
    items = await ctx.filters.blogs(clean_list(categories), clean_list(tags))
    return Listing.of([BlogFilterOut.of(item) for item in items])
