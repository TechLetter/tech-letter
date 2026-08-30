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

__all__ = ["COLLECTION", "ModelCheck", "ModelScanner", "compute_health", "run_scan"]

COLLECTION = "llm_model_checks"
_BASE_URL = "https://openrouter.ai/api/v1"
logger = get_logger(__name__)

register_indexes(
    COLLECTION,
    [
        IndexSpec(
            "idx_model_checks_model_time", [("model_id", ASCENDING), ("checked_at", DESCENDING)]
        ),
        # TTL. uptime 계산은 24시간 창만 보므로 며칠만 남겨도 충분하다.
        IndexSpec(
            "idx_model_checks_ttl", [("checked_at", ASCENDING)], expire_after_seconds=3 * 24 * 3600
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

    async def scan(self) -> list[ModelCheck]:
        model_ids = await self._list_free_models()
        semaphore = asyncio.Semaphore(max(1, self._settings.scouter_scan_concurrency))
        delay = self._settings.scouter_scan_request_delay_seconds

        async def check(index: int, model_id: str) -> ModelCheck:
            async with semaphore:
                if delay > 0:
                    await asyncio.sleep(delay * index)
                return await self._check_model(model_id)

        return list(await asyncio.gather(*(check(i, m) for i, m in enumerate(model_ids))))

    async def _list_free_models(self) -> list[str]:
        response = await self._request("GET", "/models")
        data = response.json().get("data")
        if not isinstance(data, list):
            msg = "unexpected OpenRouter /models payload"
            raise ValueError(msg)
        ids = {
            item["id"]
            for item in data
            if isinstance(item, dict) and str(item.get("id", "")).endswith(":free")
        }
        return sorted(ids)

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
    checks = await ModelScanner(settings, api_key, client).scan()
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
