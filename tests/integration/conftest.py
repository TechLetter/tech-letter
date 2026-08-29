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
