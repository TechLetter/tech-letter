"""검색 자동완성.

본 검색 결과는 `/posts?q=`가 준다 — 필터·페이지·카드 모양이 목록과 같아야 해서다.
여기는 입력하는 동안 부르는 가벼운 어휘 검색만 둔다(임베딩 호출 없음).
"""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import Ctx
from techletter.api.schemas import Listing, SearchSuggestionOut
from techletter.api.schemas.query import StrQ

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/suggest", response_model=Listing[SearchSuggestionOut])
async def suggest(ctx: Ctx, q: StrQ = None) -> Listing[SearchSuggestionOut]:
    items = await ctx.search.suggest(q)
    return Listing.of([SearchSuggestionOut.of(item) for item in items])
