"""모델×용도별 성적 기록과 자동 강등.

scouter의 "OK"는 *응답한다*는 뜻이지 *한국어 JSON 요약을 잘한다*는 뜻이 아니다.
실측에서 `cohere/north-mini-code`는 응답은 하지만 결론을 반대로 요약했다.
그래서 실제 성공률을 DB에 쌓아 나쁜 모델을 뒤로 민다.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.settings import RouterSettings

__all__ = ["COLLECTION", "ModelPurpose", "ModelStatsStore"]

COLLECTION = "llm_model_stats"
logger = get_logger(__name__)

register_indexes(
    COLLECTION,
    [
        IndexSpec(
            "idx_model_stats_purpose_attempts",
            [("purpose", 1), ("attempts", -1)],
        )
    ],
)


class ModelPurpose(StrEnum):
    SUMMARY = "summary"
    CHAT = "chat"
    PLANNER = "planner"


class ModelStatsStore:
    def __init__(self, db: AsyncDatabase, settings: RouterSettings) -> None:
        self._col = db[COLLECTION]
        self._settings = settings

    @staticmethod
    def _key(model_id: str, purpose: ModelPurpose) -> str:
        return f"{model_id}:{purpose.value}"

    async def record(self, model_id: str, purpose: ModelPurpose, *, success: bool) -> None:
        """시도·성공 횟수만 센다. 자동 강등(`demoted`)이 읽는 것이 이 둘뿐이다."""
        now = utcnow()
        await self._col.update_one(
            {"_id": self._key(model_id, purpose)},
            {
                "$inc": {"attempts": 1, "successes": int(success)},
                "$set": {"model_id": model_id, "purpose": purpose.value, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
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

    async def reset(self, model_id: str, purpose: ModelPurpose) -> None:
        await self._col.delete_one({"_id": self._key(model_id, purpose)})
