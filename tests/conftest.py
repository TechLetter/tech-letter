"""테스트 공통 픽스처."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator, Iterator

    from fastapi import FastAPI
    from httpx import AsyncClient

# 실제 .env를 읽어 로컬 환경에 따라 테스트 결과가 달라지는 것을 막는다.
_TEST_ENV = {
    "MONGO_URI": "mongodb://test:test@localhost:27017/techletter_test?authSource=admin",
    "MONGO_DB_NAME": "techletter_test",
    "JWT_SECRET": "test-secret-not-a-real-key",
    "GOOGLE_OAUTH_CLIENT_ID": "test-client-id",
    "GOOGLE_OAUTH_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_OAUTH_REDIRECT_URL": "http://localhost:8080/api/v1/auth/google/callback",
    "AUTH_LOGIN_SUCCESS_REDIRECT_URL": "http://localhost:5173/login/success",
    "CORS_ALLOWED_ORIGINS": "http://localhost:5173",
    "LOG_LEVEL": "WARNING",
    "SERVICE_NAME": "techletter-test",
}


@pytest.fixture(autouse=True, scope="session")
def _test_env() -> Iterator[None]:
    previous = {k: os.environ.get(k) for k in _TEST_ENV}
    os.environ.update(_TEST_ENV)
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def settings():
    from techletter.settings import Settings

    return Settings.load()


@pytest.fixture
def app(settings) -> FastAPI:
    from techletter.app import create_app

    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client
