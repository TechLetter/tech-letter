"""openrouter-scouter 클라이언트.

같은 호스트에서 사용자가 운영하는 서비스로, 매시간 OpenRouter의 모든 `:free`
모델을 헬스체크한다. 무료 모델은 예고 없이 사라지므로 설정에 모델을
박아두면 챗봇이 죽는다.

접근 경로: `tech-letter_default` 네트워크에 연결된 컨테이너명. 호스트 IP
방식은 클라우드 방화벽의 iptables INPUT REJECT 때문에 동작하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
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
    """헬스 목록을 TTL 캐시로 들고 있는다. scouter가 죽어도 서비스는 계속 돈다."""

    def __init__(self, settings: RouterSettings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
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

        try:
            payload = await self._fetch()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "scouter fetch failed; using fallback",
                extra={"error": str(exc)[:200], "cached": len(self._cache)},
            )
            return self._cache

        models = [ModelHealth.from_payload(item) for item in payload if isinstance(item, dict)]
        healthy = [
            m for m in models if m.is_healthy and m.uptime_24h >= self._settings.min_uptime_24h
        ]
        healthy.sort(key=lambda m: (-m.uptime_24h, m.avg_latency_ms or 1e9))
        self._cache = healthy
        self._fetched_at = now
        logger.info("scouter fetch ok", extra={"total": len(models), "healthy": len(healthy)})
        return healthy

    async def _fetch(self) -> list[Any]:
        url = f"{self._settings.scouter_base_url.rstrip('/')}/api/models"
        timeout = self._settings.scouter_timeout_seconds
        if self._client is not None:
            response = await self._client.get(url, timeout=timeout)
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            msg = f"unexpected scouter payload: {type(data).__name__}"
            raise ValueError(msg)
        return data
