"""공개 모델 상태.

챗봇에서 고를 수 있는 무료 모델이 지금 쓸 만한지를 로그인 없이 볼 수 있게 한다.
어드민 설정과 분리된 공개 API라 스키마도 따로 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import Ctx
from techletter.api.schemas import Listing, ModelHealthOut, ModelHealthSummaryOut

router = APIRouter(prefix="/llm-models", tags=["llm-models"])

DAILY_DAYS = 30


@router.get("/summary", response_model=ModelHealthSummaryOut)
async def summary(ctx: Ctx) -> ModelHealthSummaryOut:
    from techletter.core.llm.model_scan import (  # noqa: PLC0415
        compute_health,
        last_scan_at,
        summarize_health,
    )

    health = await compute_health(ctx.db)
    return ModelHealthSummaryOut.of(summarize_health(health), await last_scan_at(ctx.db))


@router.get("", response_model=Listing[ModelHealthOut])
async def list_models(ctx: Ctx) -> Listing[ModelHealthOut]:
    """모델별 현재 상태와 최근 30일 일별 가용률. 챗봇·어드민의 모델 목록도 이것을 쓴다."""
    from techletter.core.llm.model_history import history  # noqa: PLC0415
    from techletter.core.llm.model_meta import load_meta  # noqa: PLC0415
    from techletter.core.llm.model_scan import compute_health  # noqa: PLC0415
    from techletter.core.llm.recommend import candidates_from, recommend  # noqa: PLC0415

    health = await compute_health(ctx.db)
    health.sort(key=lambda m: m.get("uptime_24h") or 0.0)  # 문제 있는 것부터 보여준다
    daily: dict[str, list[dict]] = {}
    for row in await history(ctx.db, days=DAILY_DAYS):
        daily.setdefault(row["model_id"], []).append(row)
    meta = await load_meta(ctx.db)
    # 요약·챗봇이 모델을 고르는 순서와 같은 계산이다(scouter도 이 함수를 쓴다).
    recs = recommend(candidates_from(health, daily, meta), ctx.settings.router)
    items = []
    for row in health:
        model_id = str(row.get("model_id"))
        items.append(
            ModelHealthOut.of(row, daily.get(model_id, []), meta.get(model_id), recs.get(model_id))
        )
    return Listing.of(items)
