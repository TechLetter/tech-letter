"""OpenRouter 무료 모델 헬스체크 — 요청/응답 분류와 집계."""

from __future__ import annotations

import httpx
import pytest

from techletter.core.llm import model_scan
from techletter.core.llm.model_scan import ModelScanner, _aggregate
from techletter.settings import RouterSettings


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(attempt: int, base: float = 0.5, cap: float = 8.0) -> None:
        return None

    monkeypatch.setattr(model_scan, "_backoff", _noop)


def _scanner(handler, *, max_retries: int = 2) -> ModelScanner:
    settings = RouterSettings(
        scouter_scan_max_retries=max_retries,
        scouter_scan_concurrency=4,
        scouter_scan_request_delay_seconds=0.0,
    )
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return ModelScanner(settings, "test-key", client)


MODELS_PAYLOAD = {
    "data": [
        {"id": "a/free-model:free"},
        {"id": "b/paid-model"},
        {"id": "c/another-free:free"},
    ]
}


async def test_list_free_models_filters_and_sorts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json=MODELS_PAYLOAD)

    scanner = _scanner(handler)
    models = await scanner._list_free_models()

    assert models == ["a/free-model:free", "c/another-free:free"]


async def test_check_model_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    scanner = _scanner(handler)
    result = await scanner._check_model("a/free-model:free")

    assert result.ok is True
    assert result.http_status == 200
    assert result.error_category is None
    assert result.latency_ms is not None


async def test_check_model_client_error_does_not_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    scanner = _scanner(handler)
    result = await scanner._check_model("a/free-model:free")

    assert result.ok is False
    assert result.http_status == 400
    assert result.error_category == "client_error"
    assert calls == 1, "4xx(429 제외)는 재시도해도 안 풀리므로 즉시 실패해야 한다"


async def test_check_model_rate_limited_retries_then_fails() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    scanner = _scanner(handler, max_retries=2)
    result = await scanner._check_model("a/free-model:free")

    assert result.ok is False
    assert result.error_category == "rate_limited"
    assert calls == 3, "max_retries=2면 최초 시도 + 재시도 2회 = 3번"


async def test_check_model_recovers_after_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"choices": []})

    scanner = _scanner(handler, max_retries=2)
    result = await scanner._check_model("a/free-model:free")

    assert result.ok is True
    assert calls == 2


async def test_check_model_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    scanner = _scanner(handler, max_retries=1)
    result = await scanner._check_model("a/free-model:free")

    assert result.ok is False
    assert result.error_category == "network"
    assert result.http_status is None


async def test_scan_checks_every_free_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS_PAYLOAD)
        return httpx.Response(200, json={"choices": []})

    scanner = _scanner(handler)
    results = await scanner.scan()

    assert {r.model_id for r in results} == {"a/free-model:free", "c/another-free:free"}
    assert all(r.ok for r in results)


def _check(*, ok: bool, http_status: int | None = None, latency_ms: int | None = 100) -> dict:
    return {"ok": ok, "http_status": http_status, "latency_ms": latency_ms if ok else None}


def test_aggregate_computes_uptime_and_avg_latency() -> None:
    checks = [_check(ok=True, http_status=200, latency_ms=100) for _ in range(3)] + [
        _check(ok=False, http_status=500)
    ]
    # 최신이 앞에 오도록(내림차순) 실패를 맨 앞으로.
    ordered = [checks[3], checks[0], checks[1], checks[2]]

    stats = _aggregate({"m": ordered}, sample_limit=100)[0]

    assert stats["model_id"] == "m"
    assert stats["uptime_24h"] == 75.0
    assert stats["avg_latency_24h"] == 100.0
    assert stats["consecutive_failures"] == 1
    assert stats["latest_status"] == "HTTP 500"


def test_aggregate_reports_ok_when_latest_succeeds() -> None:
    ordered = [_check(ok=True), _check(ok=False, http_status=429)]

    stats = _aggregate({"m": ordered}, sample_limit=100)[0]

    assert stats["consecutive_failures"] == 0
    assert stats["latest_status"] == "OK"


def test_aggregate_labels_429_distinctly() -> None:
    ordered = [_check(ok=False, http_status=429)]

    stats = _aggregate({"m": ordered}, sample_limit=100)[0]

    assert stats["latest_status"] == "429"


def test_aggregate_respects_sample_limit() -> None:
    ordered = [_check(ok=False, http_status=500)] * 5 + [_check(ok=True)] * 5

    stats = _aggregate({"m": ordered}, sample_limit=5)[0]

    assert stats["uptime_24h"] == 0.0, "sample_limit 안에 실패만 있으면 uptime 0"


@pytest.mark.parametrize(
    ("latest_status", "uptime", "expected"),
    [
        ("OK", 99.0, "healthy"),
        ("OK", 60.0, "degraded"),
        ("OK", 10.0, "degraded"),  # 지금 응답하면 고를 수 있다
        ("429", 99.0, "down"),  # 가용률이 높아도 지금 부르면 실패한다
        ("HTTP 403", 0.0, "down"),
        ("", 100.0, "down"),
    ],
)
def test_state_means_usable_now(latest_status: str, uptime: float, expected: str) -> None:
    """모델 페이지 색과 챗봇 선택 가능 여부가 같은 기준이어야 한다."""
    from techletter.core.llm.model_scan import classify_state

    assert classify_state({"latest_status": latest_status, "uptime_24h": uptime}) == expected
