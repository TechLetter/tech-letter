"""테스트용 설정·객체 팩토리."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import SecretStr

from techletter.settings import AuthSettings

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

__all__ = ["TEST_JWT_SECRET", "TEST_REDIRECT", "clear_documents", "make_auth_settings"]

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


async def clear_documents(db: AsyncDatabase) -> None:
    """문서만 비운다. 컬렉션과 인덱스는 남겨 다음 테스트가 다시 만들지 않게 한다."""
    for name in await db.list_collection_names():
        if not name.startswith("system."):
            await db[name].delete_many({})
