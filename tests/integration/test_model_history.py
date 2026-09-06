"""모델 헬스 일별 집계."""

from __future__ import annotations

from datetime import timedelta

import pytest

from techletter.core.llm.model_history import COLLECTION, history, rollup_daily
from techletter.core.llm.model_scan import COLLECTION as CHECKS_COLLECTION
from techletter.core.time import utcnow

pytestmark = pytest.mark.integration


async def _seed(db, rows):
    await db[CHECKS_COLLECTION].delete_many({})
    await db[COLLECTION].delete_many({})
    if rows:
        await db[CHECKS_COLLECTION].insert_many(rows)


def _at(minutes: int = 0):
    """오늘 UTC 자정 + 오프셋.

    `utcnow() - 20분` 같은 상대 시각을 쓰면 실행 시각이 UTC 자정 근처일 때
    같은 테스트 안에서 날짜가 갈려 버킷 수가 달라진다.
    """
    return utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)


def _check(model_id, *, ok, at, latency_ms=None, http_status=None):
    return {
        "model_id": model_id,
        "ok": ok,
        "http_status": http_status,
        "latency_ms": latency_ms,
        "error_category": None,
        "checked_at": at,
    }


async def test_rollup_folds_checks_into_one_bucket_per_model_per_day(mongo_db):
    await _seed(
        mongo_db,
        [
            _check("a/free", ok=True, at=_at(30), latency_ms=100),
            _check("a/free", ok=True, at=_at(20), latency_ms=300),
            _check("a/free", ok=False, at=_at(10), http_status=429),
            _check("b/free", ok=True, at=_at(30), latency_ms=50),
        ],
    )

    buckets = await rollup_daily(mongo_db)

    assert buckets == 2
    rows = {r["model_id"]: r for r in await history(mongo_db, days=1)}
    a = rows["a/free"]
    assert a["checks"] == 3
    assert a["successes"] == 2
    assert a["uptime"] == pytest.approx(200 / 3)
    assert a["rate_limited"] == 1
    # 평균 지연은 성공한 체크만 센다 — 실패한 429는 빠져야 한다.
    assert a["avg_latency_ms"] == pytest.approx(200.0)
    assert rows["b/free"]["checks"] == 1


async def test_rollup_is_idempotent(mongo_db):
    await _seed(mongo_db, [_check("a/free", ok=True, at=_at(30), latency_ms=100)])

    await rollup_daily(mongo_db)
    await rollup_daily(mongo_db)

    rows = await history(mongo_db, days=1)
    assert len(rows) == 1
    assert rows[0]["checks"] == 1


async def test_rerunning_after_new_checks_updates_the_same_bucket(mongo_db):
    """오늘 버킷은 스캔이 돌 때마다 갱신돼야 한다 — 새로 쌓이면 안 된다."""
    await _seed(mongo_db, [_check("a/free", ok=True, at=_at(10), latency_ms=100)])
    await rollup_daily(mongo_db)

    await mongo_db[CHECKS_COLLECTION].insert_one(
        _check("a/free", ok=False, at=_at(30), http_status=500)
    )
    await rollup_daily(mongo_db)

    rows = await history(mongo_db, days=1)
    assert len(rows) == 1
    assert rows[0]["checks"] == 2
    assert rows[0]["successes"] == 1
    assert rows[0]["uptime"] == pytest.approx(50.0)


async def test_history_survives_raw_records_being_deleted(mongo_db):
    """집계의 존재 이유 — 원시 기록이 TTL로 사라져도 추이는 남아야 한다."""
    await _seed(mongo_db, [_check("a/free", ok=True, at=_at(30), latency_ms=100)])
    await rollup_daily(mongo_db)

    await mongo_db[CHECKS_COLLECTION].delete_many({})

    rows = await history(mongo_db, days=1)
    assert len(rows) == 1
    assert rows[0]["model_id"] == "a/free"


async def test_history_filters_by_model_and_window(mongo_db):
    await _seed(
        mongo_db,
        [
            _check("a/free", ok=True, at=_at(30), latency_ms=100),
            _check("b/free", ok=True, at=_at(30), latency_ms=100),
        ],
    )
    await rollup_daily(mongo_db)

    only_a = await history(mongo_db, model_id="a/free", days=1)
    assert [r["model_id"] for r in only_a] == ["a/free"]


async def test_rollup_with_no_checks_does_nothing(mongo_db):
    await _seed(mongo_db, [])
    assert await rollup_daily(mongo_db) == 0
    assert await history(mongo_db, days=1) == []


async def test_daily_indexes_are_created(mongo_db):
    import techletter.core.llm.model_history  # noqa: F401
    from techletter.core.db.indexes import ensure_indexes

    await ensure_indexes(mongo_db)
    info = await mongo_db[COLLECTION].index_information()
    assert "idx_model_daily_model_date" in info
    assert "idx_model_daily_ttl" in info
