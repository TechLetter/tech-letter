"""인덱스 옵션을 바꿨을 때 `ensure_indexes`가 실제 인덱스를 맞춰 주는지.

Mongo는 같은 이름에 다른 옵션으로 인덱스를 만들면 그냥 실패한다. `ensure_indexes`는
부팅 경로라, 대조 없이 만들기만 하면 TTL 하나 바꾼 순간 부팅이 깨진다.
"""

from __future__ import annotations

import pytest
from pymongo import ASCENDING

from techletter.core.db.indexes import (
    IndexSpec,
    clear_registry,
    ensure_indexes,
    register_indexes,
    registered,
)

pytestmark = pytest.mark.integration

COLLECTION = "index_reconcile_probe"


@pytest.fixture(autouse=True)
def _isolate_registry():
    """이 파일은 레지스트리를 직접 만진다 — 다른 테스트로 새지 않게 한다."""
    saved = registered()
    clear_registry()
    yield
    clear_registry()
    for collection, specs in saved.items():
        register_indexes(collection, specs)


async def _ttl_of(db, name: str) -> int | None:
    info = await db[COLLECTION].index_information()
    return info.get(name, {}).get("expireAfterSeconds")


async def test_changing_ttl_updates_the_existing_index(mongo_db):
    await mongo_db[COLLECTION].drop()
    register_indexes(
        COLLECTION,
        [
            IndexSpec(
                "idx_probe_ttl", [("checked_at", ASCENDING)], expire_after_seconds=3 * 24 * 3600
            )
        ],
    )
    await ensure_indexes(mongo_db)
    assert await _ttl_of(mongo_db, "idx_probe_ttl") == 3 * 24 * 3600

    # 배포로 TTL이 늘어난 상황.
    clear_registry()
    register_indexes(
        COLLECTION,
        [
            IndexSpec(
                "idx_probe_ttl", [("checked_at", ASCENDING)], expire_after_seconds=30 * 24 * 3600
            )
        ],
    )
    await ensure_indexes(mongo_db)

    assert await _ttl_of(mongo_db, "idx_probe_ttl") == 30 * 24 * 3600
    await mongo_db[COLLECTION].drop()


async def test_changing_unique_recreates_the_index(mongo_db):
    await mongo_db[COLLECTION].drop()
    register_indexes(COLLECTION, [IndexSpec("idx_probe_uniq", [("key", ASCENDING)])])
    await ensure_indexes(mongo_db)
    info = await mongo_db[COLLECTION].index_information()
    assert not info["idx_probe_uniq"].get("unique", False)

    clear_registry()
    register_indexes(COLLECTION, [IndexSpec("idx_probe_uniq", [("key", ASCENDING)], unique=True)])
    await ensure_indexes(mongo_db)

    info = await mongo_db[COLLECTION].index_information()
    assert info["idx_probe_uniq"]["unique"] is True
    await mongo_db[COLLECTION].drop()


async def test_unchanged_specs_are_a_noop(mongo_db):
    await mongo_db[COLLECTION].drop()
    spec = IndexSpec("idx_probe_same", [("key", ASCENDING)], expire_after_seconds=600)
    register_indexes(COLLECTION, [spec])

    first = await ensure_indexes(mongo_db)
    second = await ensure_indexes(mongo_db)

    assert first.get(COLLECTION) == ["idx_probe_same"]
    # 두 번째는 만들 게 없어야 한다 — 매 부팅마다 다시 만들면 안 된다.
    assert COLLECTION not in second
    await mongo_db[COLLECTION].drop()
