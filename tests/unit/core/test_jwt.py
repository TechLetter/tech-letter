"""JWT — 이미 발급된 운영 토큰과 호환되어야 한다."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from tests.factories import TEST_JWT_SECRET, make_auth_settings

from techletter.core.errors import AuthRequiredError, InvalidTokenError
from techletter.core.security import (
    ROLE_ADMIN,
    ROLE_USER,
    extract_bearer,
    issue_token,
    verify_token,
)
from techletter.settings import AuthSettings

SECRET = TEST_JWT_SECRET


@pytest.fixture
def auth() -> AuthSettings:
    return make_auth_settings(jwt_secret=SECRET)


def _legacy_token(payload: dict, secret: str = SECRET, alg: str = "HS256") -> str:
    """이미 발급된 것과 같은 모양의 토큰을 직접 만든다."""

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": alg, "typ": "JWT"}, separators=(",", ":")).encode())
    body = b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = b64(hmac.new(secret.encode(), header + b"." + body, hashlib.sha256).digest())
    return (header + b"." + body + b"." + sig).decode()


def test_roundtrip(auth):
    token = issue_token(auth, "google:abc", ROLE_ADMIN)
    claims = verify_token(auth, token)
    assert claims.user_code == "google:abc"
    assert claims.role == ROLE_ADMIN
    assert claims.is_admin is True


def test_default_role_is_user(auth):
    assert verify_token(auth, issue_token(auth, "google:abc")).role == ROLE_USER


def test_ttl_is_24h(auth):
    assert auth.jwt_ttl_seconds == 24 * 60 * 60


def test_accepts_existing_production_shaped_token(auth):
    """이미 발급된 것과 같은 클레임(sub/role/iss/exp)만 가진 토큰."""
    token = _legacy_token(
        {
            "sub": "google:legacy-user",
            "role": "user",
            "iss": "tech-letter",
            "exp": int(time.time()) + 3600,
        }
    )
    claims = verify_token(auth, token)
    assert claims.user_code == "google:legacy-user"


def test_missing_role_is_allowed(auth):
    """role이 없으면 빈 문자열로 통과시킨다."""
    token = _legacy_token(
        {"sub": "google:abc", "iss": "tech-letter", "exp": int(time.time()) + 3600}
    )
    claims = verify_token(auth, token)
    assert claims.role == ""
    assert claims.is_admin is False


def test_missing_sub_is_rejected(auth):
    token = _legacy_token({"role": "user", "iss": "tech-letter", "exp": int(time.time()) + 3600})
    with pytest.raises(InvalidTokenError):
        verify_token(auth, token)


def test_expired_token_is_rejected(auth):
    token = _legacy_token({"sub": "google:abc", "iss": "tech-letter", "exp": int(time.time()) - 10})
    with pytest.raises(InvalidTokenError):
        verify_token(auth, token)


def test_wrong_secret_is_rejected(auth):
    token = _legacy_token(
        {"sub": "a", "iss": "tech-letter", "exp": int(time.time()) + 3600}, secret="other"
    )
    with pytest.raises(InvalidTokenError):
        verify_token(auth, token)


def test_wrong_issuer_is_rejected(auth):
    """iss가 다르면 거부한다(이미 발급된 토큰의 iss 값과는 다른 경우만 해당)."""
    token = _legacy_token({"sub": "a", "iss": "someone-else", "exp": int(time.time()) + 3600})
    with pytest.raises(InvalidTokenError):
        verify_token(auth, token)


def test_none_algorithm_is_rejected(auth):
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=")
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": "a", "iss": "tech-letter", "exp": int(time.time()) + 3600}).encode()
    ).rstrip(b"=")
    with pytest.raises(InvalidTokenError):
        verify_token(auth, (header + b"." + body + b".").decode())


def test_garbage_token_is_rejected(auth):
    with pytest.raises(InvalidTokenError):
        verify_token(auth, "not.a.jwt")


# ── Authorization 헤더 파싱 (Go http_test.go 이식) ───────────────────


@pytest.mark.parametrize(
    ("header", "expected"),
    [("Bearer abc", "abc"), ("bearer abc", "abc"), ("BEARER  abc  ", "abc")],
)
def test_extract_bearer_accepts(header, expected):
    assert extract_bearer(header) == expected


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer", "Bearer   ", "abc"])
def test_extract_bearer_rejects(header):
    with pytest.raises(AuthRequiredError):
        extract_bearer(header)
