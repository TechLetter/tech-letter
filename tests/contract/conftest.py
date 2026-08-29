"""계약 테스트 픽스처 — 실제 앱 + 실제 Mongo.

여기서 검증하는 것은 **응답의 모양**이다. 04 문서가 기준이고, 프론트는 이
모양에만 의존한다.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from httpx import AsyncClient

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27018")
TEST_DB_NAME = "techletter_contract"

pytestmark = pytest.mark.integration

ADMIN_CODE = "google:admin"
USER_CODE = "google:alice"


@pytest.fixture
def contract_settings():
    from pydantic import SecretStr

    from techletter.settings import Settings

    settings = Settings.load()
    settings.mongo.uri = SecretStr(TEST_MONGO_URI)
    settings.mongo.db_name = TEST_DB_NAME
    return settings


@pytest.fixture
async def app(contract_settings) -> AsyncIterator[FastAPI]:
    from pymongo.errors import PyMongoError

    from techletter.app import create_app
    from techletter.container import Container

    try:
        container = await Container.open(contract_settings)
    except PyMongoError as exc:
        pytest.skip(f"테스트 Mongo에 접속할 수 없다 ({TEST_MONGO_URI}): {exc}")

    for name in await container.db.list_collection_names():
        await container.db[name].drop()
    await container.close()

    application = create_app(contract_settings)
    async with application.router.lifespan_context(application):
        yield application

    client = (await Container.open(contract_settings, create_indexes=False)).mongo
    await client.client.drop_database(TEST_DB_NAME)
    await client.close()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    from httpx import ASGITransport, AsyncClient

    # `raise_app_exceptions=False`가 필요하다. starlette은 500 응답을 보낸 뒤에도
    # 예외를 다시 올려 서버가 로그를 남기게 하는데, 테스트에서는 그것이 클라이언트
    # 쪽으로 튀어나와 실제 응답을 볼 수 없다.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as async_client:
        yield async_client


@pytest.fixture
def ctx(app):
    return app.state.container


def auth_header(settings, user_code: str = USER_CODE, role: str = "user") -> dict[str, str]:
    from techletter.core.security.tokens import issue_token

    return {"Authorization": f"Bearer {issue_token(settings.auth, user_code, role)}"}


@pytest.fixture
def user_headers(contract_settings) -> dict[str, str]:
    return auth_header(contract_settings)


@pytest.fixture
def admin_headers(contract_settings) -> dict[str, str]:
    return auth_header(contract_settings, ADMIN_CODE, "admin")


@pytest.fixture
async def seeded(ctx):
    """블로그 1개 + 요약된 포스트 3개 + 미요약 1개."""
    from datetime import UTC, datetime

    from techletter.content.models import AISummary, Blog, Post, StatusFlags

    blog = await ctx.blogs.insert(
        Blog(name="Alpha", url="https://alpha.test", rss_url="https://alpha.test/rss")
    )
    posts = []
    for index in range(3):
        posts.append(
            await ctx.posts.insert(
                Post(
                    blog_id=blog.id,
                    blog_name=blog.name,
                    title=f"제목 {index}",
                    link=f"https://alpha.test/{index}",
                    published_at=datetime(2025, 3, index + 1, tzinfo=UTC),
                    thumbnail_url="" if index == 0 else f"https://alpha.test/{index}.png",
                    plain_text=f"본문 {index}",
                    status=StatusFlags(ai_summarized=True, embedded=index == 0),
                    aisummary=AISummary(
                        categories=["Backend"],
                        tags=["Kafka"] if index else ["Kafka", "Go"],
                        summary=f"요약 {index}",
                        model_name="gemini-3-flash-preview",
                        generated_at=datetime(2025, 3, index + 1, tzinfo=UTC),
                    ),
                )
            )
        )
    unsummarized = await ctx.posts.insert(
        Post(
            blog_id=blog.id,
            blog_name=blog.name,
            title="아직 요약 안 됨",
            link="https://alpha.test/pending",
            published_at=datetime(2025, 3, 9, tzinfo=UTC),
            status=StatusFlags(),
        )
    )
    return {"blog": blog, "posts": posts, "unsummarized": unsummarized}
