"""주간 기술 흐름."""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import Ctx, MaybeUser
from techletter.api.schemas import WeeklyTrendsOut
from techletter.api.schemas.query import StrQ
from techletter.api.v1.posts import _bookmarked_ids
from techletter.core.pagination import lenient_int

router = APIRouter(prefix="/trends", tags=["trends"])

DEFAULT_LIMIT = 8
MAX_LIMIT = 30


@router.get("/weekly", response_model=WeeklyTrendsOut)
async def weekly_trends(ctx: Ctx, user: MaybeUser, limit: StrQ = None) -> WeeklyTrendsOut:
    """최근 7일 대 직전 7일. 주제별로 다룬 회사 수·글 수와 대표 글을 준다."""
    parsed = lenient_int(limit, default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT)
    result = await ctx.trends.weekly(parsed)
    post_ids = [str(post.id) for item in result.items for post in item.posts]
    return WeeklyTrendsOut.of(result, await _bookmarked_ids(ctx, user, post_ids))
