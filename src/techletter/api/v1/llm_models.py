"""공개 모델 상태.

무료 모델이 얼마나 잘 버티는지, 뭐가 새로 생기고 사라졌는지를 로그인 없이
볼 수 있게 한다 — 요약 폴백과 챗봇 자동 선택에서 참고하는 상태를 보여주는
창이다. 어드민 설정과 분리된 공개 API라 스키마도 따로 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.deps import Ctx
from techletter.api.schemas import Listing, ModelEventOut, ModelHealthOut, ModelHealthSummaryOut
from techletter.api.schemas.llm import ModelHistoryPointOut
from techletter.api.schemas.query import StrQ
from techletter.core.pagination import lenient_int

router = APIRouter(prefix="/llm-models", tags=["llm-models"])

DEFAULT_EVENTS_LIMIT = 30
MAX_EVENTS_LIMIT = 100
DEFAULT_HISTORY_DAYS = 30
PERIOD_DAYS = {"1d": 1, "1w": 7, "1m": 30, "1y": 365}


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
    from techletter.core.llm.model_scan import compute_health  # noqa: PLC0415

    health = await compute_health(ctx.db)
    health.sort(key=lambda m: m.get("uptime_24h") or 0.0)  # 문제 있는 것부터 보여준다
    return Listing.of([ModelHealthOut.of(row) for row in health])


@router.get("/events", response_model=Listing[ModelEventOut])
async def list_events(
    ctx: Ctx, model_id: StrQ = None, limit: StrQ = None
) -> Listing[ModelEventOut]:
    from techletter.core.llm.model_events import list_events as _list_events  # noqa: PLC0415

    parsed_limit = lenient_int(
        limit, default=DEFAULT_EVENTS_LIMIT, minimum=1, maximum=MAX_EVENTS_LIMIT
    )
    rows = await _list_events(ctx.db, model_id=model_id or None, limit=parsed_limit)
    return Listing.of([ModelEventOut.of(row) for row in rows])


@router.get("/{model_id:path}/history", response_model=Listing[ModelHistoryPointOut])
async def model_history(
    ctx: Ctx, model_id: str, period: StrQ = None
) -> Listing[ModelHistoryPointOut]:
    from techletter.core.llm.model_history import history  # noqa: PLC0415

    days = PERIOD_DAYS.get(period or "1m", DEFAULT_HISTORY_DAYS)
    rows = await history(ctx.db, model_id=model_id, days=days)
    return Listing.of([ModelHistoryPointOut.of(row) for row in rows])
