"""모델 헬스 일별 집계.

원시 체크 기록(`llm_model_checks`)은 스캔마다 모델 수만큼 쌓여서 오래 두기
어렵다. 그래서 하루 단위로 접어 `llm_model_daily`에 남긴다. 추이 차트는 이
집계를 읽는다 — 원시 기록의 보관 기간과 무관하게 길게 볼 수 있다.

집계는 멱등하다. 매번 최근 며칠을 통째로 다시 계산해 덮어쓰므로, 워커가
중간에 죽어 한 번 걸렀어도 다음 실행이 메운다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, DESCENDING, UpdateOne

from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.llm.model_scan import COLLECTION as CHECKS_COLLECTION
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

__all__ = ["COLLECTION", "RETENTION_DAYS", "history", "rollup_daily"]

COLLECTION = "llm_model_daily"

# 1년 추이까지 보여주고 조금 여유를 둔다. 모델 하나당 하루 한 건이라
# 60개 모델 × 400일이어도 2만 건대다 — 보관 비용이 사실상 없다.
RETENTION_DAYS = 400

# 매 실행마다 다시 계산할 범위. 오늘은 아직 진행 중이라 계속 갱신해야 하고,
# 어제까지 보는 건 자정 근처에 워커가 죽었을 때를 메우기 위한 여유다.
ROLLUP_WINDOW_DAYS = 2

logger = get_logger(__name__)

register_indexes(
    COLLECTION,
    [
        IndexSpec("idx_model_daily_model_date", [("model_id", ASCENDING), ("date", DESCENDING)]),
        IndexSpec("idx_model_daily_date", [("date", DESCENDING)]),
        IndexSpec(
            "idx_model_daily_ttl",
            [("date_at", ASCENDING)],
            expire_after_seconds=RETENTION_DAYS * 24 * 3600,
        ),
    ],
)


def _day_start(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def rollup_daily(db: AsyncDatabase, *, days: int = ROLLUP_WINDOW_DAYS) -> int:
    """최근 `days`일의 원시 기록을 날짜×모델로 접어 저장한다.

    돌려주는 값은 갱신한 (날짜, 모델) 버킷 수다.
    """
    since = _day_start(utcnow() - timedelta(days=max(days - 1, 0)))
    pipeline: list[dict[str, Any]] = [
        {"$match": {"checked_at": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "date": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$checked_at",
                            "timezone": "UTC",
                        }
                    },
                    "model_id": "$model_id",
                },
                "checks": {"$sum": 1},
                "successes": {"$sum": {"$cond": [{"$eq": ["$ok", True]}, 1, 0]}},
                "rate_limited": {"$sum": {"$cond": [{"$eq": ["$http_status", 429]}, 1, 0]}},
                # 평균 지연은 성공한 체크만 센다. 실패는 지연이 없거나 의미가 없다.
                "latency_sum": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$ok", True]}, {"$ne": ["$latency_ms", None]}]},
                            "$latency_ms",
                            0,
                        ]
                    }
                },
                "latency_count": {
                    "$sum": {
                        "$cond": [
                            {"$and": [{"$eq": ["$ok", True]}, {"$ne": ["$latency_ms", None]}]},
                            1,
                            0,
                        ]
                    }
                },
                "first_checked_at": {"$min": "$checked_at"},
                "last_checked_at": {"$max": "$checked_at"},
            }
        },
    ]

    now = utcnow()
    operations: list[UpdateOne] = []
    cursor = await db[CHECKS_COLLECTION].aggregate(pipeline)
    async for row in cursor:
        date, model_id = row["_id"]["date"], row["_id"]["model_id"]
        checks, successes = row["checks"], row["successes"]
        latency_count = row["latency_count"]
        operations.append(
            UpdateOne(
                {"_id": f"{date}:{model_id}"},
                {
                    "$set": {
                        "date": date,
                        "date_at": datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC),
                        "model_id": model_id,
                        "checks": checks,
                        "successes": successes,
                        "uptime": (successes / checks) * 100 if checks else 0.0,
                        "rate_limited": row["rate_limited"],
                        "avg_latency_ms": (
                            row["latency_sum"] / latency_count if latency_count else None
                        ),
                        "first_checked_at": row["first_checked_at"],
                        "last_checked_at": row["last_checked_at"],
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        )

    if not operations:
        logger.info("model history rollup: nothing to roll up")
        return 0

    await db[COLLECTION].bulk_write(operations, ordered=False)
    logger.info("model history rollup complete", extra={"buckets": len(operations)})
    return len(operations)


async def history(
    db: AsyncDatabase, *, model_id: str | None = None, days: int = 30
) -> list[dict[str, Any]]:
    """일별 집계를 오래된 순으로 준다. 차트가 그대로 그릴 수 있는 모양이다."""
    since = _day_start(utcnow() - timedelta(days=max(days - 1, 0))).strftime("%Y-%m-%d")
    query: dict[str, Any] = {"date": {"$gte": since}}
    if model_id is not None:
        query["model_id"] = model_id

    rows: list[dict[str, Any]] = []
    cursor = db[COLLECTION].find(query, projection={"_id": 0, "created_at": 0, "updated_at": 0})
    async for doc in cursor.sort([("date", ASCENDING), ("model_id", ASCENDING)]):
        rows.append(doc)
    return rows
