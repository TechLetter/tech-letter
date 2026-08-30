"""OpenRouter 무료 모델 헬스체크 — 실제 Mongo로 저장·집계·라우터 연동까지."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from techletter.core.llm.model_scan import COLLECTION, compute_health, run_scan
from techletter.core.llm.scouter import ScouterClient
from techletter.core.time import utcnow
from techletter.settings import RouterSettings

pytestmark = pytest.mark.integration

MODELS_PAYLOAD = {"data": [{"id": "a/model:free"}, {"id": "b/model:free"}]}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_run_scan_persists_checks(mongo_db) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS_PAYLOAD)
        return httpx.Response(200, json={"choices": []})

    settings = RouterSettings(scouter_scan_request_delay_seconds=0.0)
    saved = await run_scan(mongo_db, settings, "test-key", _client(handler))

    assert saved == 2
    docs = await mongo_db[COLLECTION].find({}).to_list(length=10)
    assert {d["model_id"] for d in docs} == {"a/model:free", "b/model:free"}
    assert all(d["ok"] for d in docs)


async def test_compute_health_ignores_checks_outside_window(mongo_db) -> None:
    now = utcnow()
    await mongo_db[COLLECTION].insert_many(
        [
            {
                "model_id": "fresh",
                "ok": True,
                "http_status": 200,
                "latency_ms": 100,
                "error_category": None,
                "checked_at": now,
            },
            {
                "model_id": "stale",
                "ok": True,
                "http_status": 200,
                "latency_ms": 100,
                "error_category": None,
                "checked_at": now - timedelta(hours=48),
            },
        ]
    )

    health = await compute_health(mongo_db, window_hours=24)

    assert {h["model_id"] for h in health} == {"fresh"}


async def test_scouter_client_reports_healthy_models_from_mongo(mongo_db) -> None:
    now = utcnow()
    await mongo_db[COLLECTION].insert_many(
        [
            {
                "model_id": "good/model:free",
                "ok": True,
                "http_status": 200,
                "latency_ms": 120,
                "error_category": None,
                "checked_at": now,
            },
            {
                "model_id": "bad/model:free",
                "ok": False,
                "http_status": 429,
                "latency_ms": None,
                "error_category": "rate_limited",
                "checked_at": now,
            },
        ]
    )

    client = ScouterClient(RouterSettings(min_uptime_24h=50.0), mongo_db)
    models = await client.healthy_models()

    assert [m.model_id for m in models] == ["good/model:free"]


async def test_scouter_client_returns_empty_without_any_checks(mongo_db) -> None:
    client = ScouterClient(RouterSettings(), mongo_db)

    assert await client.healthy_models() == []
