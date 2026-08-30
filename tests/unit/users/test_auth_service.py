"""OAuth 흐름 — 실패는 전부 쿼리 없는 302여야 한다."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from tests.factories import TEST_REDIRECT as REDIRECT
from tests.factories import make_auth_settings

from techletter.core.errors import SessionExpiredError
from techletter.users.auth_service import AuthService, GoogleOAuthError


class FakeSessions:
    def __init__(self) -> None:
        self.stored: dict[str, str] = {}

    async def create(self, session_id: str, jwt_token: str, ttl_seconds: int):
        self.stored[session_id] = jwt_token

    async def consume(self, session_id: str) -> str | None:
        return self.stored.pop(session_id, None)


def make_service(redirect: str = REDIRECT) -> tuple[AuthService, FakeSessions]:
    sessions = FakeSessions()
    service = AuthService(make_auth_settings(redirect=redirect), None, None, sessions)  # pyright: ignore[reportArgumentType]
    return service, sessions


def test_start_login_builds_google_url():
    service, _ = make_service()
    start = service.start_login()
    parsed = urlparse(start.authorize_url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "accounts.google.com"
    assert query["client_id"] == ["client-id"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid email profile"]
    assert query["state"] == [start.state]


def test_start_login_state_is_random():
    service, _ = make_service()
    assert service.start_login().state != service.start_login().state


@pytest.mark.parametrize(
    ("code", "state", "cookie"),
    [
        ("code", "abc", None),  # 쿠키 없음
        ("code", "abc", "other"),  # state 불일치
        ("code", "", "abc"),  # state 없음
        ("", "abc", "abc"),  # code 없음
    ],
)
async def test_callback_rejects_invalid_state_or_code(code, state, cookie):
    service, _ = make_service()
    with pytest.raises(GoogleOAuthError):
        await service.handle_callback(code, state, cookie)


def test_failure_redirect_has_no_query():
    service, _ = make_service()
    assert service.failure_redirect() == REDIRECT
    assert "?" not in service.failure_redirect()


def test_redirect_appends_session():
    service, _ = make_service()
    url = service._redirect_with_session("sid-123")
    assert parse_qs(urlparse(url).query)["session"] == ["sid-123"]


def test_redirect_preserves_existing_query():
    """문자열 포맷으로 조립하면 기존 쿼리가 있을 때 URL이 깨진다."""
    service, _ = make_service("http://localhost:5173/login/success?from=app")
    url = service._redirect_with_session("sid-123")
    query = parse_qs(urlparse(url).query)
    assert query["from"] == ["app"]
    assert query["session"] == ["sid-123"]


async def test_exchange_session_returns_token():
    service, sessions = make_service()
    await sessions.create("sid-1", "jwt-value", 60)
    assert await service.exchange_session("sid-1") == "jwt-value"


async def test_exchange_session_is_single_use():
    service, sessions = make_service()
    await sessions.create("sid-1", "jwt-value", 60)
    await service.exchange_session("sid-1")
    with pytest.raises(SessionExpiredError):
        await service.exchange_session("sid-1")


@pytest.mark.parametrize("value", ["", "   ", "unknown-session"])
async def test_exchange_session_rejects_bad_input(value):
    service, _ = make_service()
    with pytest.raises(SessionExpiredError):
        await service.exchange_session(value)
