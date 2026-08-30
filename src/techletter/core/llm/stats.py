"""모델×용도별 성적 기록과 자동 강등.

scouter의 "OK"는 *응답한다*는 뜻이지 *한국어 JSON 요약을 잘한다*는 뜻이 아니다.
실측에서 `cohere/north-mini-code`는 응답은 하지만 결론을 반대로 요약했다.
그래서 실제 성공률을 DB에 쌓아 나쁜 모델을 뒤로 민다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pymongo import UpdateOne

from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.settings import RouterSettings

__all__ = ["COLLECTION", "ModelPurpose", "ModelStat", "ModelStatsStore"]

COLLECTION = "llm_model_stats"
logger = get_logger(__name__)


class ModelPurpose(StrEnum):
    SUMMARY = "summary"
    CHAT = "chat"
    PLANNER = "planner"


@dataclass(frozen=True, slots=True)
class ModelStat:
    model_id: str
    purpose: str
    attempts: int
    successes: int
    json_failures: int
    rate_limited: int
    avg_latency_ms: float

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 1.0


class ModelStatsStore:
    def __init__(self, db: AsyncDatabase, settings: RouterSettings) -> None:
        self._col = db[COLLECTION]
        self._settings = settings

    @staticmethod
    def _key(model_id: str, purpose: ModelPurpose) -> str:
        return f"{model_id}:{purpose.value}"

    async def record(
        self,
        model_id: str,
        purpose: ModelPurpose,
        *,
        success: bool,
        latency_ms: float | None = None,
        json_failure: bool = False,
        rate_limited: bool = False,
        error: str | None = None,
    ) -> None:
        inc: dict[str, int] = {"attempts": 1, "successes": int(success)}
        if json_failure:
            inc["json_failures"] = 1
        if rate_limited:
            inc["rate_limited"] = 1
        if not success and not json_failure and not rate_limited:
            inc["errors"] = 1

        set_fields: dict[str, Any] = {
            "model_id": model_id,
            "purpose": purpose.value,
            "last_used_at": utcnow(),
            "updated_at": utcnow(),
        }
        if error:
            set_fields["last_error"] = error[:300]
        if latency_ms is not None:
            # 지수이동평균. 최근 성능을 반영하되 튀는 값에 흔들리지 않는다.
            existing = await self._col.find_one(
                {"_id": self._key(model_id, purpose)}, projection={"avg_latency_ms": 1}
            )
            previous = (existing or {}).get("avg_latency_ms")
            set_fields["avg_latency_ms"] = (
                latency_ms if previous is None else previous * 0.7 + latency_ms * 0.3
            )

        await self._col.update_one(
            {"_id": self._key(model_id, purpose)},
            {"$inc": inc, "$set": set_fields, "$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )

    async def demoted(self, purpose: ModelPurpose) -> set[str]:
        """성공률이 임계 미만인 모델. 후보 순서에서 뒤로 민다."""
        demoted: set[str] = set()
        cursor = self._col.find(
            {
                "purpose": purpose.value,
                "attempts": {"$gte": self._settings.min_attempts_for_demotion},
            }
        )
        async for doc in cursor:
            attempts = doc.get("attempts") or 0
            rate = (doc.get("successes") or 0) / attempts if attempts else 1.0
            if rate < self._settings.min_success_rate:
                demoted.add(doc["model_id"])
        return demoted

    async def all_stats(self, purpose: ModelPurpose | None = None) -> list[dict[str, Any]]:
        """어드민 대시보드용(04 §3.10)."""
        query = {"purpose": purpose.value} if purpose else {}
        rows: list[dict[str, Any]] = []
        cursor = self._col.find(query)
        async for doc in cursor:
            attempts = doc.get("attempts") or 0
            rows.append(
                {
                    "model_id": doc.get("model_id"),
                    "purpose": doc.get("purpose"),
                    "attempts": attempts,
                    "successes": doc.get("successes", 0),
                    "json_failures": doc.get("json_failures", 0),
                    "rate_limited": doc.get("rate_limited", 0),
                    "success_rate": round(
                        (doc.get("successes", 0) / attempts) if attempts else 1.0, 3
                    ),
                    "avg_latency_ms": doc.get("avg_latency_ms"),
                    "last_used_at": doc.get("last_used_at"),
                    "last_error": doc.get("last_error"),
                }
            )
        rows.sort(key=lambda r: (-r["success_rate"], r["avg_latency_ms"] or 1e9))
        return rows

    async def reset(self, model_id: str, purpose: ModelPurpose) -> None:
        await self._col.delete_one({"_id": self._key(model_id, purpose)})

    async def bulk_record(self, operations: list[UpdateOne]) -> None:  # pragma: no cover
        if operations:
            await self._col.bulk_write(operations, ordered=False)
