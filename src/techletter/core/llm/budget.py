"""provider별 일일 사용량 예산.

요약은 Gemini를 1순위로 쓰되 일일 20회(무료 티어 한도)까지만 쓰고,
초과분은 OpenRouter로 흘린다. 예산을 넘기면 429를 맞고 잡이 재시도되는
낭비를 미리 막는다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from techletter.core.jobs.policy import next_quota_reset
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from pymongo.asynchronous.database import AsyncDatabase

__all__ = ["COLLECTION", "DailyBudget"]

COLLECTION = "llm_daily_usage"
logger = get_logger(__name__)


class DailyBudget:
    """`{date}:{provider}` 단위 카운터.

    쿼터 리셋 시각(기본 07:00 UTC = 태평양 자정)을 기준으로 날짜를 센다.
    UTC 자정으로 세면 Gemini 리셋과 어긋나 예산이 하루 걸쳐 새어 나간다.
    """

    def __init__(self, db: AsyncDatabase, *, reset_utc_hour: int = 7) -> None:
        self._col = db[COLLECTION]
        self._reset_utc_hour = reset_utc_hour

    def _bucket(self, now: datetime | None = None) -> str:
        now = now or utcnow()
        # 리셋 시각 이전이면 전날 버킷에 속한다.
        anchor = now - timedelta(hours=self._reset_utc_hour)
        return anchor.strftime("%Y-%m-%d")

    def _key(self, provider: str, now: datetime | None = None) -> str:
        return f"{self._bucket(now)}:{provider}"

    async def used(self, provider: str) -> int:
        doc = await self._col.find_one({"_id": self._key(provider)}, projection={"count": 1})
        return int((doc or {}).get("count") or 0)

    async def remaining(self, provider: str, limit: int) -> int:
        if limit <= 0:
            return 0
        return max(limit - await self.used(provider), 0)

    async def has_room(self, provider: str, limit: int) -> bool:
        """limit이 0 이하면 '예산 개념 없음'으로 보고 항상 허용한다."""
        if limit <= 0:
            return True
        return await self.used(provider) < limit

    async def consume(self, provider: str, amount: int = 1) -> int:
        now = utcnow()
        doc = await self._col.find_one_and_update(
            {"_id": self._key(provider, now)},
            {
                "$inc": {"count": amount},
                "$set": {"provider": provider, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=True,
        )
        return int((doc or {}).get("count") or amount)

    def next_reset(self, now: datetime | None = None) -> datetime:
        return next_quota_reset(now or utcnow(), self._reset_utc_hour)
