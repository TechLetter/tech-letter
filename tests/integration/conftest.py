"""통합 테스트용 실제 MongoDB 픽스처.

로컬: `docker run -d -p 27018:27017 mongo:8.2`
CI:   서비스 컨테이너(스텝 9.4에서 추가)

`TEST_MONGO_URI`로 주소를 바꿀 수 있다. 접속되지 않으면 skip한다.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator

    from pymongo.asynchronous.database import AsyncDatabase

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27018")
TEST_DB_NAME = "techletter_itest"
TEST_QDRANT_HOST = os.environ.get("TEST_QDRANT_HOST", "localhost")
TEST_QDRANT_PORT = int(os.environ.get("TEST_QDRANT_PORT", "6334"))

pytestmark = pytest.mark.integration


@pytest.fixture
async def mongo_db() -> AsyncIterator[AsyncDatabase]:
    from pymongo import AsyncMongoClient
    from pymongo.errors import PyMongoError

    client = AsyncMongoClient(TEST_MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=2000)
    try:
        await client.admin.command("ping")
    except PyMongoError as exc:
        await client.close()
        pytest.skip(f"테스트 Mongo에 접속할 수 없다 ({TEST_MONGO_URI}): {exc}")

    db = client[TEST_DB_NAME]
    for name in await db.list_collection_names():
        await db[name].drop()

    # 운영과 같은 인덱스를 만들어 둔다. 유니크 제약에 기대는 동작(중복 지급 방지,
    # 북마크 중복 등)이 인덱스 없이는 조용히 통과하기 때문이다.
    import techletter.content.repositories
    import techletter.core.jobs.queue
    import techletter.users.repositories  # noqa: F401
    from techletter.core.db.indexes import ensure_indexes

    await ensure_indexes(db)
    try:
        yield db
    finally:
        await client.drop_database(TEST_DB_NAME)
        await client.close()


@pytest.fixture
def job_settings():
    from techletter.settings import JobSettings

    # 테스트에서는 폴링을 빠르게 돌린다. alias가 있는 필드는 alias로 준다.
    return JobSettings(JOB_POLL_INTERVAL_SECONDS=0.01, idle_backoff_seconds=0.02)


@pytest.fixture
def queue(mongo_db, job_settings):
    from techletter.core.jobs import JobQueue, RetryPolicy

    return JobQueue(mongo_db, job_settings, RetryPolicy(job_settings, quota_reset_utc_hour=7))


@pytest.fixture
async def vector_store():
    """실제 Qdrant. `docker run -d -p 6334:6333 qdrant/qdrant`.

    컬렉션 이름 규칙과 필터 삭제는 대역으로 검증되지 않는다.
    """
    from techletter.core.db.qdrant import VectorStore
    from techletter.settings import QdrantSettings

    settings = QdrantSettings(
        QDRANT_HOST=TEST_QDRANT_HOST,
        QDRANT_PORT=TEST_QDRANT_PORT,
        QDRANT_COLLECTION_NAME="techletter_itest",
    )
    store = VectorStore(settings)
    try:
        await store.ping()
    except Exception as exc:
        await store.close()
        pytest.skip(
            f"테스트 Qdrant에 접속할 수 없다 ({TEST_QDRANT_HOST}:{TEST_QDRANT_PORT}): {exc}"
        )

    yield store

    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(host=TEST_QDRANT_HOST, port=TEST_QDRANT_PORT)
    for collection in (await client.get_collections()).collections:
        if collection.name.startswith("techletter_itest"):
            await client.delete_collection(collection.name)
    await client.close()
    await store.close()
