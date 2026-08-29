"""테스트용 설정·객체 팩토리."""

from __future__ import annotations

from pydantic import SecretStr

from techletter.settings import AuthSettings

__all__ = ["TEST_JWT_SECRET", "TEST_REDIRECT", "make_auth_settings"]

TEST_JWT_SECRET = "test-secret-not-a-real-key-at-least-32-bytes"
TEST_REDIRECT = "http://localhost:5173/login/success"


def make_auth_settings(
    *,
    jwt_secret: str = TEST_JWT_SECRET,
    issuer: str = "tech-letter",
    redirect: str = TEST_REDIRECT,
) -> AuthSettings:
    return AuthSettings(
        JWT_SECRET=SecretStr(jwt_secret),
        JWT_ISSUER=issuer,
        GOOGLE_OAUTH_CLIENT_ID="client-id",
        GOOGLE_OAUTH_CLIENT_SECRET=SecretStr("client-secret"),
        GOOGLE_OAUTH_REDIRECT_URL="http://localhost:8080/api/v1/auth/google/callback",
        AUTH_LOGIN_SUCCESS_REDIRECT_URL=redirect,
    )
