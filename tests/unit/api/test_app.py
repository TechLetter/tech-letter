"""앱 부트스트랩·미들웨어·에러 핸들러."""

from __future__ import annotations


async def test_health_is_degraded_before_the_container_is_ready(client):
    """수명주기를 열지 않은 앱은 아직 준비되지 않았다.

    부팅 중에 200을 내면 배포가 그대로 통과해 버린다. 정상 경로는 계약
    테스트(`test_health_reports_ok`)가 실제 Mongo로 확인한다.
    """
    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "checks": {"mongo": "starting"}}


async def test_request_id_is_echoed(client):
    response = await client.get("/health", headers={"X-Request-Id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"


async def test_request_id_is_generated_when_absent(client):
    response = await client.get("/health")
    assert response.headers.get("x-request-id")


async def test_unknown_route_uses_error_envelope(client):
    """404도 같은 단일 에러 봉투를 쓴다."""
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
    """FastAPI 기본 422를 쓰지 않는다 — 계약에 422가 없다."""
    from pydantic import BaseModel

    class Body(BaseModel):
        count: int

    @app.post("/_test/validate")
    async def _validate(_: Body) -> dict:
        return {}

    response = await client.post("/_test/validate", json={"count": "not-a-number"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "request.invalid"


async def test_unhandled_exception_does_not_leak_internals(app):
    """starlette은 500을 보낸 뒤에도 예외를 다시 올린다(서버 로그용).

    그래서 실제 응답을 보려면 `raise_app_exceptions=False`가 필요하다.
    """
    from httpx import ASGITransport, AsyncClient

    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("secret detail: mongodb://user:pw@host")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/_test/boom")

    assert response.status_code == 500
    assert "mongodb://" not in response.text
    assert response.json()["error"]["code"] == "internal.error"


def test_openapi_is_generated(app):
    schema = app.openapi()
    assert schema["info"]["title"] == "Tech-Letter API"
