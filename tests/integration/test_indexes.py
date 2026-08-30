"""인덱스 레지스트리 — 이름·키·옵션이 실제 운영 DB와 일치해야 한다.

이름이 다르면 같은 키에 중복 인덱스가 생긴다.
"""

from __future__ import annotations

import pytest

from techletter.core.db.indexes import ensure_indexes, registered
from techletter.core.jobs.types import COLLECTION, JobStatus

pytestmark = pytest.mark.integration


async def test_jobs_indexes_are_created_with_expected_names(mongo_db):
    await ensure_indexes(mongo_db)
    info = await mongo_db[COLLECTION].index_information()

    assert "idx_jobs_claim" in info
    assert "idx_jobs_stale" in info
    assert "idx_jobs_dedupe" in info
    assert "ttl_jobs_done" in info


async def test_claim_index_key_order(mongo_db):
    """클레임 쿼리는 {status,type} 동등 + {priority,run_at} 정렬이다."""
    await ensure_indexes(mongo_db)
    info = await mongo_db[COLLECTION].index_information()
    assert info["idx_jobs_claim"]["key"] == [
        ("status", 1),
        ("type", 1),
        ("priority", 1),
        ("run_at", 1),
    ]


async def test_done_ttl_is_partial(mongo_db):
    """완료된 잡만 자동 삭제한다. dead는 사람이 볼 때까지 남아야 한다."""
    await ensure_indexes(mongo_db)
    info = await mongo_db[COLLECTION].index_information()
    ttl = info["ttl_jobs_done"]
    assert ttl["expireAfterSeconds"] == 14 * 24 * 3600
    assert ttl["partialFilterExpression"] == {"status": JobStatus.DONE.value}


async def test_ensure_indexes_is_idempotent(mongo_db):
    first = await ensure_indexes(mongo_db)
    second = await ensure_indexes(mongo_db)
    assert first == second


async def test_registry_contains_jobs_collection():
    # queue 모듈을 import하면 등록된다
    from techletter.core.jobs import queue as _queue  # noqa: F401

    assert COLLECTION in registered()


async def test_model_checks_indexes_are_created(mongo_db):
    from techletter.core.llm import model_scan

    await ensure_indexes(mongo_db)
    info = await mongo_db[model_scan.COLLECTION].index_information()

    assert "idx_model_checks_model_time" in info
    assert info["idx_model_checks_ttl"]["expireAfterSeconds"] == 3 * 24 * 3600
