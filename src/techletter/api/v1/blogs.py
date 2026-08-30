"""블로그 목록."""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import Ctx
from techletter.api.schemas import BlogOut, Paged
from techletter.api.schemas.query import StrQ, parse_page

router = APIRouter(prefix="/blogs", tags=["blogs"])


@router.get("", response_model=Paged[BlogOut])
async def list_blogs(
    ctx: Ctx,
    page: StrQ = None,
    page_size: StrQ = None,
) -> Paged[BlogOut]:
    paging = parse_page(page, page_size, default_size=100)
    blogs, total = await ctx.blogs.list_blogs(paging)
    return Paged.of_page([BlogOut.of(blog) for blog in blogs], total, paging)
