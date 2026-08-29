"""모델 성적 (04 §3.10, §4.4).

"어떤 무료 모델이 실제로 쓸 만한가"를 화면에서 본다. 챗봇이 죽은 모델을
가리킨 채 방치되던 상황(ISSUE-021)을 눈에 보이게 만드는 것이 목적이다.
"""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import Listing, LlmModelStatOut
from techletter.api.schemas.query import StrQ
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


async def _health_by_model(ctx: Ctx) -> dict[str, dict[str, object]]:
    """scouter 헬스. 죽어 있어도 통계는 보여야 하므로 실패를 삼킨다."""
    from techletter.core.llm.scouter import ScouterClient  # noqa: PLC0415

    try:
        models = await ScouterClient(ctx.settings.router, ctx.http.get()).healthy_models()
    except Exception:
        logger.warning("scouter unavailable; reporting stats without health")
        return {}
    return {
        model.model_id: {"healthy": model.is_healthy, "uptime_24h": model.uptime_24h}
        for model in models
    }
