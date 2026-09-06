"""모델 카탈로그 변동 감지.

스캔마다 무료 모델 목록·헬스를 이전 스캔의 상태와 비교해서, 사람이 신경 쓸
만한 변화만 이벤트로 남긴다 — "이 모델이 새로 생겼다/사라졌다/저하됐다/
복구됐다". 매 스캔 원시 기록만 봐서는 이런 변화를 알아채기 어렵다.

`llm_model_catalog`에 모델별 "지금까지 알고 있던 상태"를 한 건씩 유지하고,
이번 스캔 결과와 그 상태를 diff해서 이벤트를 만든 뒤 카탈로그를 갱신한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, DESCENDING, UpdateOne

from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.core.llm.model_scan import ModelCheck

__all__ = [
    "CATALOG_COLLECTION",
    "EVENTS_COLLECTION",
    "EventType",
    "detect_and_record",
    "list_events",
]

CATALOG_COLLECTION = "llm_model_catalog"
EVENTS_COLLECTION = "llm_model_events"

# 이벤트 피드는 "최근에 무슨 일이 있었는지" 훑어보는 용도라 원시 기록보다
# 훨씬 길게, 그래도 무한하지는 않게 남긴다.
EVENT_RETENTION_DAYS = 90

logger = get_logger(__name__)

register_indexes(
    EVENTS_COLLECTION,
    [
        IndexSpec("idx_model_events_detected", [("detected_at", DESCENDING)]),
        IndexSpec("idx_model_events_model", [("model_id", ASCENDING), ("detected_at", DESCENDING)]),
        IndexSpec(
            "idx_model_events_ttl",
            [("detected_at", ASCENDING)],
            expire_after_seconds=EVENT_RETENTION_DAYS * 24 * 3600,
        ),
    ],
)


class EventType(StrEnum):
    MODEL_ADDED = "model_added"
    MODEL_REMOVED = "model_removed"
    MODEL_DEGRADED = "model_degraded"
    MODEL_RECOVERED = "model_recovered"


@dataclass(frozen=True, slots=True)
class _CatalogEntry:
    model_id: str
    is_active: bool
    consecutive_failures: int
    degraded: bool
    first_seen_at: Any
    last_seen_at: Any


def _diff(
    previous: dict[str, _CatalogEntry],
    checks: list[ModelCheck],
    *,
    degrade_threshold: int,
    now: Any,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """이번 스캔과 이전 카탈로그를 비교해 (이벤트 목록, 카탈로그 갱신분)을 준다.

    순수 함수다 — DB를 몰라야 스캔 1회 결과만으로 유닛 테스트할 수 있다.
    """
    events: list[dict[str, Any]] = []
    updates: dict[str, dict[str, Any]] = {}
    current_ids = {c.model_id for c in checks}

    for check in checks:
        prior = previous.get(check.model_id)
        if prior is None or not prior.is_active:
            events.append(
                {
                    "model_id": check.model_id,
                    "type": EventType.MODEL_ADDED.value,
                    "detected_at": now,
                    "reason": None,
                }
            )
            updates[check.model_id] = {
                "is_active": True,
                "consecutive_failures": 0 if check.ok else 1,
                "degraded": False,
                "first_seen_at": (prior.first_seen_at if prior else now),
                "last_seen_at": now,
            }
            continue

        consecutive_failures = 0 if check.ok else prior.consecutive_failures + 1
        degraded = consecutive_failures >= degrade_threshold
        if degraded and not prior.degraded:
            events.append(
                {
                    "model_id": check.model_id,
                    "type": EventType.MODEL_DEGRADED.value,
                    "detected_at": now,
                    "reason": check.error_category,
                }
            )
        elif not degraded and prior.degraded:
            events.append(
                {
                    "model_id": check.model_id,
                    "type": EventType.MODEL_RECOVERED.value,
                    "detected_at": now,
                    "reason": None,
                }
            )
        updates[check.model_id] = {
            "is_active": True,
            "consecutive_failures": consecutive_failures,
            "degraded": degraded,
            "first_seen_at": prior.first_seen_at,
            "last_seen_at": now,
        }

    for model_id, prior in previous.items():
        if prior.is_active and model_id not in current_ids:
            events.append(
                {
                    "model_id": model_id,
                    "type": EventType.MODEL_REMOVED.value,
                    "detected_at": now,
                    "reason": None,
                }
            )
            updates[model_id] = {
                "is_active": False,
                "consecutive_failures": 0,
                "degraded": False,
                "first_seen_at": prior.first_seen_at,
                "last_seen_at": prior.last_seen_at,
            }

    return events, updates


async def detect_and_record(
    db: AsyncDatabase, checks: list[ModelCheck], *, degrade_threshold: int = 2
) -> int:
    """이번 스캔 결과를 카탈로그와 비교해 이벤트를 남기고 카탈로그를 갱신한다.

    돌려주는 값은 이번에 새로 남긴 이벤트 수다.
    """
    if not checks:
        return 0

    now = utcnow()
    previous: dict[str, _CatalogEntry] = {}
    async for doc in db[CATALOG_COLLECTION].find({}):
        previous[doc["_id"]] = _CatalogEntry(
            model_id=doc["_id"],
            is_active=bool(doc.get("is_active")),
            consecutive_failures=int(doc.get("consecutive_failures") or 0),
            degraded=bool(doc.get("degraded")),
            first_seen_at=doc.get("first_seen_at"),
            last_seen_at=doc.get("last_seen_at"),
        )

    events, updates = _diff(previous, checks, degrade_threshold=degrade_threshold, now=now)

    if events:
        await db[EVENTS_COLLECTION].insert_many(events)
    if updates:
        await db[CATALOG_COLLECTION].bulk_write(
            [
                UpdateOne({"_id": model_id}, {"$set": fields}, upsert=True)
                for model_id, fields in updates.items()
            ],
            ordered=False,
        )

    if events:
        logger.info("model catalog changes detected", extra={"events": len(events)})
    return len(events)


async def list_events(
    db: AsyncDatabase, *, model_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """최신순 이벤트 피드."""
    query: dict[str, Any] = {}
    if model_id is not None:
        query["model_id"] = model_id

    rows: list[dict[str, Any]] = []
    cursor = (
        db[EVENTS_COLLECTION].find(query, projection={"_id": 0}).sort("detected_at", DESCENDING)
    )
    async for doc in cursor.limit(limit):
        rows.append(doc)
    return rows
