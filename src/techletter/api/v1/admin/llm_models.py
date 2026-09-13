"""요약 모델 폴백 체인 설정."""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import (
    Listing,
    LlmModelPreferenceIn,
    LlmModelPreferenceOut,
)
from techletter.core.errors import InvalidRequestError
from techletter.core.llm.stats import ModelPurpose

router = APIRouter(prefix="/llm-models", tags=["admin:llm"])


@router.get("/preferences", response_model=Listing[LlmModelPreferenceOut])
async def list_preferences(ctx: Ctx, _: AdminUser) -> Listing[LlmModelPreferenceOut]:
    """요약 폴백 체인과 환경변수 기본값을 반환한다."""
    rows = await ctx.model_preferences.all_preferences()
    return Listing.of([LlmModelPreferenceOut.of(row) for row in rows])


@router.put("/preferences/{purpose}", response_model=LlmModelPreferenceOut)
async def set_preference(
    ctx: Ctx, _: AdminUser, purpose: str, body: LlmModelPreferenceIn
) -> LlmModelPreferenceOut:
    """후보 중에서 고른 목록을 저장한다. 재배포 없이 다음 호출부터 적용된다."""
    if purpose not in set(ModelPurpose):
        msg = f"알 수 없는 용도: {purpose}"
        raise InvalidRequestError(msg, details={"field": "purpose"})

    target = ModelPurpose(purpose)
    await ctx.model_preferences.set_preference(target, body.models)
    rows = await ctx.model_preferences.all_preferences()
    return LlmModelPreferenceOut.of(rows[0])
