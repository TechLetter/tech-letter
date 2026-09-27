"""한도가 있는 모델(Gemini 무료 등급)을 한도 안에서만 부른다.

요약은 3 Flash(하루 20회) → 3.5 Flash Lite(하루 450회) → OpenRouter 무료 모델
순서로 시도한다. 앞의 두 모델은 하루·분당 한도가 있다. 이 모듈이 **호출 직전에**
한도를 확인하고 센다. 그래서 후보 목록에는 한도 모델을 전부 세워 둘 수 있다.
3 Flash가 503·429로 실패하면 라우터가 다음 후보인 3.5 Flash Lite로 넘어간다.

- 하루 예산이 다 찼으면 `QuotaSkipped`를 던진다. 라우터는 이 모델을 성적에 적지
  않고 다음 후보로 간다.
- 분당 한도에 닿았으면 다음 모델로 넘기지 않고 기다린다. 429 → 폴백보다 싸다.
- 구글이 일일 한도 429를 주면 장부를 한도까지 채운다. 리셋 전까지 다시 부르지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.errors import QuotaExceededError
from techletter.core.logging import get_logger
from techletter.core.ratelimit import MinuteRateLimiter

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from techletter.core.llm.budget import DailyBudget

__all__ = ["QuotaGate", "QuotaModel", "QuotaSkipped", "is_daily_quota_error"]

logger = get_logger(__name__)

# 구글 429 본문의 quotaId. 분당 한도는 `...PerMinute...`라 여기 걸리지 않는다.
_DAILY_QUOTA = re.compile(r"per ?day", re.I)


def is_daily_quota_error(exc: BaseException) -> bool:
    return bool(_DAILY_QUOTA.search(str(exc)))


class QuotaSkipped(QuotaExceededError):  # noqa: N818 — 실패가 아니라 "건너뜀"이다
    """오늘 예산을 다 쓴 모델. 라우터는 성적에 적지 않고 다음 후보로 간다.

    후보가 전부 이것이면 잡 큐는 쿼터 리셋까지 기다린다(`QuotaExceededError`).
    """


@dataclass(frozen=True, slots=True)
class QuotaModel:
    model_id: str
    budget_key: str
    """`llm_daily_usage` 장부 키. 키를 바꾸면 오늘 쓴 양을 잊는다."""
    daily_limit: int
    """0 이하면 하루 한도를 세지 않는다."""
    per_minute: int = 0
    """0 이하면 분당 한도를 세지 않는다."""


class QuotaGate:
    def __init__(self, budget: DailyBudget, models: Sequence[QuotaModel]) -> None:
        self._budget = budget
        self._models = {m.model_id: m for m in models if m.model_id}
        self._limiters = {
            m.model_id: MinuteRateLimiter(m.per_minute) for m in self._models.values()
        }

    @property
    def model_ids(self) -> list[str]:
        """시도 순서대로."""
        return list(self._models)

    async def acquire(self, model_id: str) -> None:
        """한 번 부를 자리를 잡는다. 한도 모델이 아니면 아무것도 하지 않는다.

        실패한 호출도 구글 한도를 깎으므로 부르기 전에 센다.
        """
        model = self._models.get(model_id)
        if model is None:
            return
        # 예산을 먼저 본다. 다 쓴 모델 때문에 분당 한도를 기다리지 않는다.
        if not await self._budget.has_room(model.budget_key, model.daily_limit):
            raise QuotaSkipped(f"{model_id}: daily budget spent")
        await self._limiters[model_id].acquire(1)
        await self._budget.consume(model.budget_key)

    async def exhaust(self, model_id: str) -> None:
        """구글이 일일 한도라고 답했다. 장부를 한도까지 채운다."""
        model = self._models.get(model_id)
        if model is None or model.daily_limit <= 0:
            return
        await self._budget.fill(model.budget_key, model.daily_limit)
        logger.warning("provider reported daily quota spent", extra={"model": model_id})
