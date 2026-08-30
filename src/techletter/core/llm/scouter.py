"""OpenRouter 무료 모델 헬스 정보.

`core/llm/model_scan.py`가 주기적으로 쌓는 헬스체크 기록을 집계해 라우터에
넘긴다. TTL 캐시로 들고 있어 매 LLM 호출마다 DB를 다시 조회하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
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
        """정상 모델을 uptime 내림차순·지연 오름차순으로 준다.

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
        healthy = [
            m for m in models if m.is_healthy and m.uptime_24h >= self._settings.min_uptime_24h
        ]
        healthy.sort(key=lambda m: (-m.uptime_24h, m.avg_latency_ms or 1e9))
        self._cache = healthy
        self._fetched_at = now
        logger.info("model health computed", extra={"total": len(models), "healthy": len(healthy)})
        return healthy
