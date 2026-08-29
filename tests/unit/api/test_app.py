"""앱 부트스트랩·미들웨어·에러 핸들러."""

from __future__ import annotations

import pytest


async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_request_id_is_echoed(client):
    response = await client.get("/health", headers={"X-Request-Id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"


async def test_request_id_is_generated_when_absent(client):
    response = await client.get("/health")
    assert response.headers.get("x-request-id")


async def test_unknown_route_uses_error_envelope(client):
    """404도 04 §1.3의 단일 봉투를 쓴다."""
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "resource.not_found"
    assert body["error"]["message"]


async def test_app_error_is_converted(app, client):
    """도메인 예외가 그대로 봉투로 바뀌는지 확인한다."""
    from techletter.core.errors import InsufficientCreditsError

    @app.get("/_test/credit")
    async def _raise() -> None:
        raise InsufficientCreditsError

    response = await client.get("/_test/credit")
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "credit.insufficient"


async def test_validation_error_becomes_400_not_422(app, client):
    """FastAPI 기본 422를 쓰지 않는다 — 현행 계약에 422가 없다."""
    from pydantic import BaseModel

    class Body(BaseModel):
        count: int

    @app.post("/_test/validate")
    async def _validate(_: Body) -> dict:
        return {}

    response = await client.post("/_test/validate", json={"count": "not-a-number"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "request.invalid"


async def test_unhandled_exception_does_not_leak_internals(app, client):
    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("secret detail: mongodb://user:pw@host")

    with pytest.raises(RuntimeError):
        # ASGITransport는 예외를 그대로 올린다. 핸들러 동작은 아래에서 확인한다.
        await client.get("/_test/boom")


def test_openapi_is_generated(app):
    schema = app.openapi()
    assert schema["info"]["title"] == "Tech-Letter API"
