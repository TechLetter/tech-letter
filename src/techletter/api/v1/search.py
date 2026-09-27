"""검색 자동완성과 검색 결과 AI 요약.

본 검색 결과는 `/posts?q=`가 준다 — 필터·페이지·카드 모양이 목록과 같아야 해서다.
자동완성은 입력하는 동안 부르는 가벼운 어휘 검색이다(임베딩 호출 없음).
AI 요약은 크레딧 없이 로그인 사용자에게 준다(`search/summary.py`).
"""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import Ctx, CurrentUser
from techletter.api.schemas import (
    Listing,
    SearchSuggestionOut,
    SearchSummaryContinueIn,
    SearchSummaryIn,
    SearchSummaryOut,
)
from techletter.api.schemas.query import StrQ

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/suggest", response_model=Listing[SearchSuggestionOut])
async def suggest(ctx: Ctx, q: StrQ = None) -> Listing[SearchSuggestionOut]:
    items = await ctx.search.suggest(q)
    return Listing.of([SearchSuggestionOut.of(item) for item in items])


@router.post("/summary", response_model=SearchSummaryOut)
async def summary(ctx: Ctx, user: CurrentUser, body: SearchSummaryIn) -> SearchSummaryOut:
    result = await ctx.search_summary.summarize(user.user_code, body.query, body.post_ids)
    return SearchSummaryOut.of(result)


@router.post("/summary/continue")
async def continue_summary(
    ctx: Ctx, user: CurrentUser, body: SearchSummaryContinueIn
) -> dict[str, str]:
    """요약의 질문과 답을 담은 챗봇 세션을 만든다("이어서 묻기")."""
    return {"session_id": await ctx.search_summary.continue_in_chat(user.user_code, body.key)}
