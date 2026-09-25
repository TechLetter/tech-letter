"""OpenRouter 무료 모델 헬스체크.

주기적으로 OpenRouter의 `:free` 모델 전체에 짧은 chat completion을 보내
살아있는지 확인하고 결과를 Mongo에 쌓는다. `ScouterClient`가 이 기록으로
모델별 uptime·평균 지연·연속 실패를 계산해 라우터에 넘긴다.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import httpx
from pymongo import ASCENDING, DESCENDING

from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.settings import RouterSettings

__all__ = [
    "COLLECTION",
    "ModelCheck",
    "ModelScanner",
    "compute_health",
    "last_scan_at",
    "run_scan",
    "summarize_health",
]

COLLECTION = "llm_model_checks"
_BASE_URL = "https://openrouter.ai/api/v1"
logger = get_logger(__name__)

register_indexes(
    COLLECTION,
    [
        IndexSpec(
            "idx_model_checks_model_time", [("model_id", ASCENDING), ("checked_at", DESCENDING)]
        ),
        # TTL. 라우팅에는 24시간 창이면 충분하지만, 원시 기록은 일별 집계
        # (`model_history`)의 재료이기도 하다. 집계가 며칠 밀려도 메울 수 있게
        # 한 달은 남긴다 — 모델 하나당 하루 24건이라 보관 비용이 크지 않다.
        IndexSpec(
            "idx_model_checks_ttl", [("checked_at", ASCENDING)], expire_after_seconds=30 * 24 * 3600
        ),
    ],
)


@dataclass(frozen=True, slots=True)
class ModelCheck:
    model_id: str
    ok: bool
    http_status: int | None
    latency_ms: int | None
    error_category: str | None
    checked_at: datetime


class ModelScanner:
    """OpenRouter `:free` 모델 전체에 짧은 요청을 보내 살아있는지 확인한다."""

    def __init__(
        self, settings: RouterSettings, api_key: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._api_key = api_key
        self._client = client
        self.meta: dict[str, dict[str, Any]] = {}
        """마지막 스캔에서 읽은 모델 정보(`model_meta`). `run_scan`이 카탈로그에 담는다."""

    async def scan(self) -> list[ModelCheck]:
        model_ids = await self._list_free_models()
        semaphore = asyncio.Semaphore(max(1, self._settings.scouter_scan_concurrency))
        delay = self._settings.scouter_scan_request_delay_seconds

        async def check(index: int, model_id: str) -> ModelCheck:
            async with semaphore:
                if delay > 0:
                    await asyncio.sleep(delay * index)
                result = await self._check_model(model_id)
                self.meta.setdefault(model_id, {}).update(await self._endpoint_meta(model_id))
                return result

        return list(await asyncio.gather(*(check(i, m) for i, m in enumerate(model_ids))))

    async def _list_free_models(self) -> list[str]:
        from techletter.core.llm.model_meta import model_meta  # noqa: PLC0415

        response = await self._request("GET", "/models")
        data = response.json().get("data")
        if not isinstance(data, list):
            msg = "unexpected OpenRouter /models payload"
            raise ValueError(msg)
        free = [
            item
            for item in data
            if isinstance(item, dict) and str(item.get("id", "")).endswith(":free")
        ]
        self.meta = {item["id"]: model_meta(item) for item in free}
        return sorted(self.meta)

    async def _endpoint_meta(self, model_id: str) -> dict[str, Any]:
        """제공사·양자화. 부가 정보라 실패해도 스캔을 막지 않는다."""
        from techletter.core.llm.model_meta import endpoint_meta  # noqa: PLC0415

        try:
            response = await self._request("GET", f"/models/{model_id}/endpoints")
            return endpoint_meta(response.json()) if response.status_code < 400 else {}
        except (httpx.HTTPError, ValueError):
            return {}

    async def _check_model(self, model_id: str) -> ModelCheck:
        max_retries = self._settings.scouter_scan_max_retries
        last_status: int | None = None
        last_category = "unexpected"
        started = time.monotonic()

        for attempt in range(max_retries + 1):
            try:
                response = await self._request(
                    "POST",
                    "/chat/completions",
                    json={
                        "model": model_id,
                        "messages": [
                            {"role": "user", "content": self._settings.scouter_scan_prompt}
                        ],
                        "max_tokens": 32,
                        "temperature": 0,
                    },
                )
            except httpx.HTTPError:
                last_category = "network"
                if attempt < max_retries:
                    await _backoff(attempt)
                    continue
                return self._result(
                    model_id, ok=False, http_status=None, category=last_category, started=started
                )

            last_status = response.status_code
            if response.status_code < 400:
                return self._result(
                    model_id, ok=True, http_status=last_status, category=None, started=started
                )
            if response.status_code == 429:
                last_category = "rate_limited"
            elif response.status_code >= 500:
                last_category = "server_error"
            else:
                # 4xx(429 제외)는 재시도해도 안 풀린다 — 즉시 실패로 기록한다.
                return self._result(
                    model_id,
                    ok=False,
                    http_status=last_status,
                    category="client_error",
                    started=started,
                )

            if attempt < max_retries:
                await _backoff(attempt)
                continue
            return self._result(
                model_id, ok=False, http_status=last_status, category=last_category, started=started
            )

        return self._result(
            model_id, ok=False, http_status=last_status, category=last_category, started=started
        )

    def _result(
        self,
        model_id: str,
        *,
        ok: bool,
        http_status: int | None,
        category: str | None,
        started: float,
    ) -> ModelCheck:
        return ModelCheck(
            model_id=model_id,
            ok=ok,
            http_status=http_status,
            latency_ms=int((time.monotonic() - started) * 1000),
            error_category=category,
            checked_at=utcnow(),
        )

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        url = f"{_BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        timeout = self._settings.scouter_timeout_seconds
        if self._client is not None:
            return await self._client.request(
                method, url, headers=headers, json=json, timeout=timeout
            )
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(method, url, headers=headers, json=json)


async def _backoff(attempt: int, base: float = 0.5, cap: float = 8.0) -> None:
    await asyncio.sleep(min(cap, base * (2**attempt)))


async def run_scan(
    db: AsyncDatabase,
    settings: RouterSettings,
    api_key: str,
    client: httpx.AsyncClient | None = None,
) -> int:
    """스캔을 돌리고 결과를 저장한다. 저장한 건수를 준다."""
    from techletter.core.llm.model_events import detect_and_record  # noqa: PLC0415
    from techletter.core.llm.model_meta import save_meta  # noqa: PLC0415

    scanner = ModelScanner(settings, api_key, client)
    checks = await scanner.scan()
    if checks:
        await db[COLLECTION].insert_many(
            [
                {
                    "model_id": c.model_id,
                    "ok": c.ok,
                    "http_status": c.http_status,
                    "latency_ms": c.latency_ms,
                    "error_category": c.error_category,
                    "checked_at": c.checked_at,
                }
                for c in checks
            ]
        )
        # 카탈로그 변동 감지는 이번 스캔 원시 결과가 있어야 의미가 있다 —
        # 같은 사이클 안에서 저장 직후 바로 한다.
        await detect_and_record(
            db, checks, degrade_threshold=settings.model_event_degrade_threshold
        )
        await save_meta(db, scanner.meta)
    logger.info(
        "model scan complete",
        extra={"total": len(checks), "ok": sum(1 for c in checks if c.ok)},
    )
    return len(checks)


def _aggregate(
    records_by_model: dict[str, list[dict[str, Any]]], *, sample_limit: int
) -> list[dict[str, Any]]:
    """모델별 uptime·평균 지연·연속 실패·최신 상태 계산(순수 함수).

    각 리스트는 `checked_at` 내림차순(최신 먼저)으로 이미 정렬돼 있다고 가정한다.
    """
    results: list[dict[str, Any]] = []
    for model_id, all_checks in records_by_model.items():
        checks = all_checks[:sample_limit]
        total = len(checks)
        success = sum(1 for c in checks if c["ok"])
        uptime = (success / total) * 100 if total else 0.0
        latencies = [c["latency_ms"] for c in checks if c["ok"] and c.get("latency_ms") is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else None

        consecutive_failures = 0
        for c in checks:
            if c["ok"]:
                break
            consecutive_failures += 1

        latest = checks[0]
        if latest["ok"]:
            latest_status = "OK"
        elif latest.get("http_status") == 429:
            latest_status = "429"
        elif latest.get("http_status"):
            latest_status = f"HTTP {latest['http_status']}"
        else:
            latest_status = "FAIL"

        results.append(
            {
                "model_id": model_id,
                "uptime_24h": uptime,
                "avg_latency_24h": avg_latency,
                "consecutive_failures": consecutive_failures,
                "latest_status": latest_status,
            }
        )
    return results


async def compute_health(
    db: AsyncDatabase, *, window_hours: int = 24, sample_limit: int = 100
) -> list[dict[str, Any]]:
    """최근 `window_hours` 안의 체크 기록으로 모델별 헬스를 계산한다."""
    since = utcnow() - timedelta(hours=window_hours)
    by_model: dict[str, list[dict[str, Any]]] = {}
    cursor = db[COLLECTION].find({"checked_at": {"$gte": since}}).sort("checked_at", DESCENDING)
    async for doc in cursor:
        by_model.setdefault(doc["model_id"], []).append(doc)
    return _aggregate(by_model, sample_limit=sample_limit)


async def last_scan_at(db: AsyncDatabase) -> datetime | None:
    """가장 최근 스캔 시각. 기록이 없으면 None(아직 한 번도 안 돌았거나 TTL로 다 지워짐)."""
    doc = await db[COLLECTION].find_one({}, sort=[("checked_at", DESCENDING)])
    return doc["checked_at"] if doc else None


# 모델 페이지의 일별 막대 색과 같은 경계다(90% 이상 초록, 50% 이상 노랑, 그 아래 빨강).
HEALTHY_UPTIME = 90.0
USABLE_UPTIME = 50.0


def classify_state(model: dict[str, Any]) -> str:
    """지금 쓸 수 있는가로 3단 분류한다. 모델 페이지·챗봇 선택·추천 순위·요약 숫자가 같이 쓴다.

    - down: 마지막 체크가 실패했거나 24시간 가용률이 50% 미만. 한 번 운 좋게 응답했다고
      10번 중 8번 실패하는 모델을 쓸 수 있다고 하지 않는다.
    - degraded: 지금 응답하고 24시간 가용률 50~90%.
    - healthy: 지금 응답하고 24시간 가용률 90% 이상.
    """
    uptime = float(model.get("uptime_24h") or 0.0)
    if str(model.get("latest_status") or "").upper() != "OK" or uptime < USABLE_UPTIME:
        return "down"
    if uptime >= HEALTHY_UPTIME:
        return "healthy"
    return "degraded"


def summarize_health(health: list[dict[str, Any]]) -> dict[str, Any]:
    """공개 요약 숫자(순수 함수). 목록의 `state`와 같은 기준으로 센다."""
    counts = {"healthy": 0, "degraded": 0, "down": 0}
    for model in health:
        counts[classify_state(model)] += 1
    healthy, degraded, down = counts["healthy"], counts["degraded"], counts["down"]
    return {
        "total_models": len(health),
        "healthy_count": healthy,
        "degraded_count": degraded,
        "down_count": down,
    }
