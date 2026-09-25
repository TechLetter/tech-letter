"""모델 카탈로그 변동 감지 — 실제 Mongo에 걸쳐서."""

from __future__ import annotations

import pytest

from techletter.core.llm.model_events import (
    CATALOG_COLLECTION,
    EVENTS_COLLECTION,
    EventType,
    detect_and_record,
)
from techletter.core.llm.model_scan import ModelCheck
from techletter.core.time import utcnow


async def list_events(db, model_id: str | None = None) -> list[dict]:
    """감지 결과 확인용. 공개 API가 없어져 테스트에서 컬렉션을 직접 읽는다."""
    query = {"model_id": model_id} if model_id else {}
    cursor = db[EVENTS_COLLECTION].find(query, projection={"_id": 0}).sort("detected_at", -1)
    return [doc async for doc in cursor]


pytestmark = pytest.mark.integration


def _check(model_id: str, *, ok: bool, category: str | None = None) -> ModelCheck:
    return ModelCheck(
        model_id=model_id,
        ok=ok,
        http_status=None if ok else 429,
        latency_ms=100 if ok else None,
        error_category=category,
        checked_at=utcnow(),
    )


@pytest.fixture(autouse=True)
async def _clean(mongo_db):
    await mongo_db[CATALOG_COLLECTION].delete_many({})
    await mongo_db[EVENTS_COLLECTION].delete_many({})


async def test_first_scan_adds_every_model(mongo_db):
    count = await detect_and_record(
        mongo_db, [_check("a/free", ok=True), _check("b/free", ok=True)]
    )

    assert count == 2
    events = await list_events(mongo_db)
    assert {e["model_id"] for e in events} == {"a/free", "b/free"}
    assert all(e["type"] == EventType.MODEL_ADDED.value for e in events)


async def test_second_scan_of_the_same_healthy_models_adds_nothing(mongo_db):
    await detect_and_record(mongo_db, [_check("a/free", ok=True)])

    count = await detect_and_record(mongo_db, [_check("a/free", ok=True)])

    assert count == 0


async def test_state_persists_across_calls_to_build_a_full_lifecycle(mongo_db):
    """추가 -> 저하(2회 연속 실패) -> 복구 -> 삭제, 스캔 4번에 걸쳐."""
    await detect_and_record(mongo_db, [_check("a/free", ok=True)])  # added

    r1 = await detect_and_record(mongo_db, [_check("a/free", ok=False)])
    assert r1 == 0  # 1회 실패는 아직 저하 아님(기본 임계치 2)

    r2 = await detect_and_record(mongo_db, [_check("a/free", ok=False)])
    events_after_r2 = await list_events(mongo_db, model_id="a/free")
    assert r2 == 1
    assert events_after_r2[0]["type"] == EventType.MODEL_DEGRADED.value

    r3 = await detect_and_record(mongo_db, [_check("a/free", ok=True)])
    events_after_r3 = await list_events(mongo_db, model_id="a/free")
    assert r3 == 1
    assert events_after_r3[0]["type"] == EventType.MODEL_RECOVERED.value

    # 다음 스캔엔 a/free가 없고 다른 모델만 있다 — 진짜 "사라짐" 시나리오.
    r4 = await detect_and_record(mongo_db, [_check("b/free", ok=True)])
    events_after_r4 = await list_events(mongo_db, model_id="a/free")
    assert r4 == 2  # a/free REMOVED + b/free ADDED
    assert events_after_r4[0]["type"] == EventType.MODEL_REMOVED.value


async def test_an_empty_scan_result_does_not_wipe_the_catalog(mongo_db):
    """스캔 자체가 빈 리스트를 주면(예: 상위 API 일시 장애) 감지를 건너뛴다.

    안 그러면 일시적 장애 한 번에 모든 모델이 REMOVED로 찍힌다.
    """
    await detect_and_record(mongo_db, [_check("a/free", ok=True)])  # ADDED, 1건

    count = await detect_and_record(mongo_db, [])

    assert count == 0
    # 여전히 ADDED 1건뿐이어야 한다 — REMOVED가 새로 안 생겼다.
    assert len(await list_events(mongo_db, model_id="a/free")) == 1
    catalog = await mongo_db[CATALOG_COLLECTION].find_one({"_id": "a/free"})
    assert catalog is not None
    assert catalog["is_active"] is True


async def test_custom_degrade_threshold_is_respected(mongo_db):
    await detect_and_record(mongo_db, [_check("a/free", ok=True)])

    count = await detect_and_record(mongo_db, [_check("a/free", ok=False)], degrade_threshold=1)

    assert count == 1
    events = await list_events(mongo_db)
    assert events[0]["type"] == EventType.MODEL_DEGRADED.value


async def test_empty_scan_does_nothing_when_catalog_is_empty(mongo_db):
    assert await detect_and_record(mongo_db, []) == 0
    assert await list_events(mongo_db) == []


async def test_model_events_indexes_are_created(mongo_db):
    import techletter.core.llm.model_events  # noqa: F401
    from techletter.core.db.indexes import ensure_indexes

    await ensure_indexes(mongo_db)
    info = await mongo_db[EVENTS_COLLECTION].index_information()
    assert "idx_model_events_detected" in info
    assert "idx_model_events_ttl" in info
