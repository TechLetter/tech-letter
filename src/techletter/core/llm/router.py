"""LLM 모델 라우터.

무료 모델이 사라져도 서비스가 죽지 않게 한다.

후보 = 큐레이션 선호목록 ∩ scouter 정상목록, 성적이 나쁜 모델은 뒤로.
후보를 순서대로 시도하고 429/JSON 실패면 다음 모델로 넘어간다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar

from techletter.core.errors import PermanentError, RetryableError
from techletter.core.llm.errors import JsonOutputError, classify_llm_error
from techletter.core.llm.stats import ModelPurpose
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from techletter.core.llm.scouter import ModelHealth
    from techletter.settings import RouterSettings

__all__ = ["HealthSource", "ModelAttempt", "ModelRouter", "StatsSink", "truncate_for_model"]


class HealthSource(Protocol):
    """scouter 등 모델 헬스 공급자."""

    async def healthy_models(self) -> list[ModelHealth]: ...


class StatsSink(Protocol):
    """모델 성적 기록소."""

    async def demoted(self, purpose: ModelPurpose) -> set[str]: ...

    async def record(self, model_id: str, purpose: ModelPurpose, *, success: bool) -> None: ...


logger = get_logger(__name__)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ModelAttempt:
    model_id: str
    ok: bool
    latency_ms: float
    error: str | None = None


class ModelRouter:
    def __init__(
        self,
        settings: RouterSettings,
        scouter: HealthSource,
        stats: StatsSink | None = None,
    ) -> None:
        self._settings = settings
        self._scouter = scouter
        self._stats = stats

    async def candidates(self, purpose: ModelPurpose) -> list[str]:
        """시도할 모델을 순서대로 준다.

        1. 정상 모델 전체 (24h 가용률 높은 순, 같으면 지연 짧은 순 — scouter가 정렬)
        2. scouter가 죽었으면 정적 폴백
        성적이 나쁜 모델은 뒤로 민다. 요약은 이 앞에 Gemini를 하루 예산만큼 먼저 쓴다
        (`Summarizer`).
        """
        healthy = await self._scouter.healthy_models()
        ordered = [m.model_id for m in healthy]
        if not ordered:
            ordered = list(self._settings.static_fallback)
            if ordered:
                logger.warning("using static fallback models", extra={"purpose": purpose.value})

        if self._stats is not None and ordered:
            demoted = await self._stats.demoted(purpose)
            if demoted:
                good = [m for m in ordered if m not in demoted]
                bad = [m for m in ordered if m in demoted]
                ordered = good + bad
        return ordered[: max(self._settings.max_model_attempts, 1)]

    async def run(
        self,
        purpose: ModelPurpose,
        call: Callable[[str], Awaitable[T]],
        *,
        candidates: list[str] | None = None,
    ) -> tuple[T, str]:
        """후보를 순서대로 시도하고 (결과, 사용한 모델)을 준다.

        - `JsonOutputError`: 같은 모델을 다시 시도하지 않고 다음 모델로.
        - 쿼터/레이트리밋: 다음 모델로. 전부 실패하면 마지막 원인을 올린다.
        - `PermanentError`: 입력·프롬프트 문제이므로 즉시 전파한다.
        """
        models = candidates if candidates is not None else await self.candidates(purpose)
        if not models:
            msg = "사용 가능한 모델이 없다 (scouter/정적 폴백 모두 비어 있음)"
            raise RetryableError(msg)

        last_error: Exception | None = None
        for model_id in models:
            try:
                result = await call(model_id)
            except PermanentError:
                await self._record(model_id, purpose, ok=False)
                raise
            except JsonOutputError as exc:
                last_error = exc
                await self._record(model_id, purpose, ok=False)
                logger.warning(
                    "model returned invalid json; trying next",
                    extra={"model_id": model_id, "purpose": purpose.value},
                )
                continue
            except Exception as exc:
                classified = classify_llm_error(exc)
                last_error = classified
                await self._record(model_id, purpose, ok=False)
                if isinstance(classified, PermanentError):
                    raise classified from exc
                logger.warning(
                    "model call failed; trying next",
                    extra={
                        "model_id": model_id,
                        "purpose": purpose.value,
                        "error": str(exc)[:200],
                    },
                )
                continue
            else:
                await self._record(model_id, purpose, ok=True)
                return result, model_id

        assert last_error is not None
        logger.error(
            "all models failed",
            extra={"purpose": purpose.value, "tried": len(models)},
        )
        raise last_error

    async def _record(self, model_id: str, purpose: ModelPurpose, *, ok: bool) -> None:
        if self._stats is None:
            return
        try:
            await self._stats.record(model_id, purpose, success=ok)
        except Exception:
            logger.warning("failed to record model stats", extra={"model_id": model_id})


def truncate_for_model(text: str, max_chars: int) -> tuple[str, bool]:
    """입력을 자른다. 무료 모델은 컨텍스트가 작고 과금/지연도 입력에 비례한다."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
