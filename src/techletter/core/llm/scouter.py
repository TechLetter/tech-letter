"""OpenRouter 무료 모델 헬스 정보.

`core/llm/model_scan.py`가 주기적으로 쌓는 헬스체크 기록을 집계하고, 추천 점수
(`core/llm/recommend.py`) 순으로 줄 세워 라우터에 넘긴다. TTL 캐시로 들고 있어 매 LLM
호출마다 DB를 다시 조회하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.settings import RouterSettings

__all__ = ["ModelHealth", "ScouterClient"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModelHealth:
    model_id: str
    uptime_24h: float
    avg_latency_ms: float
    consecutive_failures: int
    latest_status: str
    rank: int | None = None
    """추천 순위(`core/llm/recommend.py`). 1이 먼저."""

    @property
    def is_healthy(self) -> bool:
        return self.latest_status.upper() == "OK" and self.consecutive_failures == 0

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> ModelHealth:
        return cls(
            model_id=str(raw.get("model_id", "")),
            uptime_24h=float(raw.get("uptime_24h") or 0.0),
            avg_latency_ms=float(raw.get("avg_latency_24h") or 0.0),
            consecutive_failures=int(raw.get("consecutive_failures") or 0),
            latest_status=str(raw.get("latest_status") or ""),
        )


class ScouterClient:
    """헬스 목록을 TTL 캐시로 들고 있는다. 조회 실패해도 서비스는 계속 돈다."""

    def __init__(self, settings: RouterSettings, db: AsyncDatabase) -> None:
        self._settings = settings
        self._db = db
        self._cache: list[ModelHealth] = []
        self._fetched_at: float = 0.0

    async def healthy_models(self) -> list[ModelHealth]:
        """쓸 수 있는 모델(정상·불안정)을 추천 순위대로 준다.

        조회 실패 시 마지막으로 성공한 캐시를 쓰고, 그것도 없으면 빈 목록을
        준다(호출자가 정적 폴백으로 넘어간다).
        """
        now = utcnow().timestamp()
        if self._cache and now - self._fetched_at < self._settings.scouter_cache_ttl_seconds:
            return self._cache

        from techletter.core.llm.model_scan import compute_health  # noqa: PLC0415

        try:
            payload = await compute_health(self._db)
        except Exception as exc:
            logger.warning(
                "model health query failed; using cache",
                extra={"error": str(exc)[:200], "cached": len(self._cache)},
            )
            return self._cache

        models = [ModelHealth.from_payload(item) for item in payload]
        healthy = await self._ranked(models, payload)
        self._cache = healthy
        self._fetched_at = now
        logger.info("model health computed", extra={"total": len(models), "healthy": len(healthy)})
        return healthy

    async def _ranked(
        self, models: list[ModelHealth], payload: list[dict[str, Any]]
    ) -> list[ModelHealth]:
        """추천 순위가 있는 모델만 순위대로. 순위를 못 구하면 지금 응답하는 모델을 가용률순으로."""
        from techletter.core.llm.recommend import load_recommendations  # noqa: PLC0415

        try:
            recs = await load_recommendations(self._db, self._settings, payload)
        except Exception as exc:
            logger.warning("model recommendation failed", extra={"error": str(exc)[:200]})
            usable = [m for m in models if m.is_healthy]
            return sorted(usable, key=lambda m: (-m.uptime_24h, m.avg_latency_ms or 1e9))
        ranked = [
            replace(m, rank=rec.rank)
            for m in models
            if (rec := recs.get(m.model_id)) is not None and rec.rank is not None
        ]
        return sorted(ranked, key=lambda m: m.rank or 0)
