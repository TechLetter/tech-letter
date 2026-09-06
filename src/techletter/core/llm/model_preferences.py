"""용도별 모델 선호목록 저장소.

선호목록은 원래 `*_MODEL_PREFERENCE` 환경변수였다. 스캐너는 1시간마다 어떤
무료 모델이 살아 있는지 알고 있는데, 정작 그걸 반영하려면 사람이 시크릿을
고치고 재배포해야 했다. 그래서 DB로 옮겼다 — 어드민이 후보 중에서 고르면
다음 캐시 만료 때 반영된다.

**환경변수는 여전히 기본값이다.** DB에 해당 용도의 선호목록이 없으면 설정을
그대로 쓴다. 그래서 이 기능을 배포해도 어드민이 손대기 전까지는 동작이
달라지지 않는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from techletter.core.llm.stats import ModelPurpose
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.settings import RouterSettings

__all__ = ["COLLECTION", "ModelPreferenceStore"]

COLLECTION = "llm_model_preferences"

# 어드민이 목록을 바꾸면 이 시간 안에 반영된다. 매 LLM 호출마다 DB를 보지
# 않으려는 것뿐이라 환경변수로 뺄 만한 값이 아니다.
CACHE_TTL_SECONDS = 60.0

logger = get_logger(__name__)


class ModelPreferenceStore:
    """`{purpose: [model_id, ...]}`. DB에 없으면 설정값으로 떨어진다."""

    def __init__(self, db: AsyncDatabase, settings: RouterSettings) -> None:
        self._col = db[COLLECTION]
        self._settings = settings
        self._cache: dict[str, list[str]] = {}
        self._fetched_at: float = 0.0

    def _from_settings(self, purpose: ModelPurpose) -> list[str]:
        if purpose is ModelPurpose.SUMMARY:
            return list(self._settings.summary_preference)
        if purpose is ModelPurpose.PLANNER:
            # 플래너는 따로 안 정했으면 챗봇 목록을 쓴다.
            return list(self._settings.planner_preference or self._settings.chat_preference)
        return list(self._settings.chat_preference)

    async def _load(self) -> dict[str, list[str]]:
        now = utcnow().timestamp()
        if self._cache and now - self._fetched_at < CACHE_TTL_SECONDS:
            return self._cache

        try:
            stored: dict[str, list[str]] = {}
            async for doc in self._col.find({}):
                models = [str(m) for m in (doc.get("models") or [])]
                if models:
                    stored[str(doc["_id"])] = models
        except Exception as exc:
            # DB가 흔들려도 라우팅은 계속돼야 한다. 캐시가 있으면 그걸 쓰고,
            # 없으면 빈 값을 줘서 호출자가 설정값으로 떨어지게 한다.
            logger.warning(
                "model preference query failed; falling back",
                extra={"error": str(exc)[:200], "cached": len(self._cache)},
            )
            return self._cache

        self._cache = stored
        self._fetched_at = now
        return stored

    async def preference(self, purpose: ModelPurpose) -> list[str]:
        stored = await self._load()
        return stored.get(purpose.value) or self._from_settings(purpose)

    async def set_preference(self, purpose: ModelPurpose, models: list[str]) -> list[str]:
        """어드민이 고른 목록을 저장한다. 빈 목록이면 설정값으로 되돌린다."""
        cleaned = [m.strip() for m in models if m and m.strip()]
        now = utcnow()
        if not cleaned:
            await self._col.delete_one({"_id": purpose.value})
        else:
            await self._col.update_one(
                {"_id": purpose.value},
                {
                    "$set": {"purpose": purpose.value, "models": cleaned, "updated_at": now},
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        self.invalidate()
        logger.info(
            "model preference updated",
            extra={"purpose": purpose.value, "count": len(cleaned)},
        )
        return cleaned or self._from_settings(purpose)

    async def all_preferences(self) -> list[dict[str, Any]]:
        """어드민 화면용. 설정에서 온 값인지 DB에서 온 값인지 구분해서 준다."""
        stored = await self._load()
        return [
            {
                "purpose": purpose.value,
                "models": stored.get(purpose.value) or self._from_settings(purpose),
                "source": "database" if stored.get(purpose.value) else "settings",
            }
            for purpose in ModelPurpose
        ]

    def invalidate(self) -> None:
        self._cache = {}
        self._fetched_at = 0.0
