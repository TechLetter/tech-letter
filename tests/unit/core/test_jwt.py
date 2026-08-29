"""JWT — 기존 운영 토큰과 호환되어야 한다(제약 C3).

Go `cmd/api/auth/jwt_test.go`와 `http_test.go`의 케이스를 이식했다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from pydantic import SecretStr

from techletter.core.errors import AuthRequiredError, InvalidTokenError
from techletter.core.security import (
    ROLE_ADMIN,
    ROLE_USER,
    extract_bearer,
    issue_token,
    verify_token,
)
from techletter.settings import AuthSettings

SECRET = "test-secret-not-a-real-key"


@pytest.fixture
def auth() -> AuthSettings:
    return AuthSettings(
        JWT_SECRET=SecretStr(SECRET),
        JWT_ISSUER="tech-letter",
        GOOGLE_OAUTH_CLIENT_ID="cid",
        GOOGLE_OAUTH_CLIENT_SECRET=SecretStr("csecret"),
        GOOGLE_OAUTH_REDIRECT_URL="http://localhost/cb",
        AUTH_LOGIN_SUCCESS_REDIRECT_URL="http://localhost/login/success",
    )


def _legacy_token(payload: dict, secret: str = SECRET, alg: str = "HS256") -> str:
    """현행 Go 구현이 만드는 것과 같은 모양의 토큰을 직접 만든다."""

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
    """현행 Go가 발급한 것과 같은 클레임(sub/role/iss/exp)만 가진 토큰."""
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
    """현행은 role이 없어도 빈 문자열로 통과시켰다."""
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
    """현행은 iss를 검증하지 않았다. v2에서 검증을 추가한다(기존 토큰은 통과)."""
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
