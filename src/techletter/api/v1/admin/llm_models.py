"""모델 성적.

"어떤 무료 모델이 실제로 쓸 만한가"를 화면에서 본다 — 설정이 죽은 모델을
가리킨 채 방치되는 상황을 눈에 보이게 만드는 것이 목적이다.
"""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import (
    Listing,
    LlmModelPreferenceIn,
    LlmModelPreferenceOut,
    LlmModelStatOut,
)
from techletter.api.schemas.query import StrQ
from techletter.core.errors import InvalidRequestError
from techletter.core.llm.stats import ModelPurpose
from techletter.core.logging import get_logger

router = APIRouter(prefix="/llm-models", tags=["admin:llm"])
logger = get_logger(__name__)


@router.get("", response_model=Listing[LlmModelStatOut])
async def list_model_stats(
    ctx: Ctx, _: AdminUser, purpose: StrQ = None
) -> Listing[LlmModelStatOut]:
    target = None
    if purpose and purpose.strip() in set(ModelPurpose):
        target = ModelPurpose(purpose.strip())

    rows = await ctx.model_stats.all_stats(target)
    health = await _health_by_model(ctx)
    stats = [LlmModelStatOut.of(row, health.get(str(row.get("model_id")))) for row in rows]
    # 성공률이 낮은 것부터 보여준다 — 문제를 찾으러 오는 화면이다.
    stats.sort(key=lambda s: (s.success_rate, -s.attempts))
    return Listing.of(stats)


@router.get("/preferences", response_model=Listing[LlmModelPreferenceOut])
async def list_preferences(ctx: Ctx, _: AdminUser) -> Listing[LlmModelPreferenceOut]:
    """용도별로 지금 무엇을 우선해서 쓰는지, 그리고 그게 어디서 온 값인지."""
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
    models = await ctx.model_preferences.set_preference(target, body.models)
    return LlmModelPreferenceOut.of(
        {
            "purpose": target.value,
            "models": models,
            "source": "database" if body.models else "settings",
        }
    )


async def _health_by_model(ctx: Ctx) -> dict[str, dict[str, object]]:
    """모델 헬스. 최근 스캔 기록이 없어도 통계는 보여야 하므로 실패를 삼킨다."""
    from techletter.core.llm.scouter import ScouterClient  # noqa: PLC0415

    try:
        models = await ScouterClient(ctx.settings.router, ctx.db).healthy_models()
    except Exception:
        logger.warning("model health unavailable; reporting stats without health")
        return {}
    return {
        model.model_id: {"healthy": model.is_healthy, "uptime_24h": model.uptime_24h}
        for model in models
    }
