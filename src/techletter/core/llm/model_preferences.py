"""요약 모델 폴백 체인 저장소.

요약 체인의 첫 후보는 `SUMMARY_MODEL_PREFERENCE` 환경변수로 정하고, 어드민이
고른 모델은 DB에 추가 후보로 저장한다. 실제 순서는 환경변수 모델을 먼저 둔 뒤
DB 모델을 이어 붙이고 중복을 제거하므로, 배포 기본값과 운영 중 조정을 함께
유지할 수 있다.

챗봇과 플래너는 사용자의 선택 또는 헬스 기반 자동 라우팅만 사용하므로 이
저장소에서 선호목록을 제공하지 않는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from techletter.core.errors import InvalidRequestError
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
    """요약 모델 체인을 `{env 기본값 + DB 추가분}`으로 관리한다."""

    def __init__(self, db: AsyncDatabase, settings: RouterSettings) -> None:
        self._col = db[COLLECTION]
        self._settings = settings
        self._cache: dict[str, list[str]] = {}
        self._fetched_at: float = 0.0

    @staticmethod
    def _unique(models: list[str]) -> list[str]:
        return list(dict.fromkeys(models))

    def settings_default(self, purpose: ModelPurpose) -> list[str]:
        """환경변수에서 온 요약 기본값만 반환한다."""
        if purpose is not ModelPurpose.SUMMARY:
            return []
        return self._unique(list(self._settings.summary_preference))

    def _merged(self, stored: list[str]) -> list[str]:
        return self._unique([*self.settings_default(ModelPurpose.SUMMARY), *stored])

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
        if purpose is not ModelPurpose.SUMMARY:
            return []
        stored = await self._load()
        return self._merged(stored.get(purpose.value, []))

    async def set_preference(self, purpose: ModelPurpose, models: list[str]) -> list[str]:
        """요약 모델 추가 후보만 저장한다. 빈 목록이면 DB 값을 지운다."""
        if purpose is not ModelPurpose.SUMMARY:
            raise InvalidRequestError(
                "요약 모델 선호목록만 설정할 수 있습니다.",
                details={"field": "purpose"},
            )

        cleaned = self._unique([m.strip() for m in models if m and m.strip()])
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
        return await self.preference(purpose)

    async def all_preferences(self) -> list[dict[str, Any]]:
        """어드민 화면용 요약 체인 한 건을 반환한다."""
        stored = await self._load()
        default_models = self.settings_default(ModelPurpose.SUMMARY)
        stored_models = stored.get(ModelPurpose.SUMMARY.value, [])
        return [
            {
                "purpose": ModelPurpose.SUMMARY.value,
                "models": self._merged(stored_models),
                "source": "database" if stored_models else "settings",
                "default_models": default_models,
            }
        ]

    def invalidate(self) -> None:
        self._cache = {}
        self._fetched_at = 0.0
