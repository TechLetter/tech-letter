"""재시도 정책 (ADR-0004 §3).

핵심은 **쿼터 실패를 재시도 횟수로 소모하지 않는 것**이다. 현행은 재시도 창이
1h46m으로 일일 쿼터 리셋(24h)보다 짧아, 쿼터로 실패한 잡이 100% DLQ로 갔다
(ISSUE-001, 미요약 526건).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from techletter.core.errors import PermanentError, QuotaExceededError, RetryableError
from techletter.core.jobs.types import ErrorKind
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from techletter.settings import JobSettings

__all__ = ["Decision", "RetryPolicy", "dead_retryable_alert", "next_quota_reset"]

_JITTER_SECONDS = 120


def dead_retryable_alert(count: int, threshold: int) -> str | None:
    """`retryable`로 dead 처리된 잡이 임계치를 넘으면 경고 문구를 준다.

    `permanent`(봇 차단·404)는 상시 발생하는 정상 노이즈지만(08 §4),
    `retryable`이 dead까지 간 건 재시도를 다 써도 안 풀린 문제라 사람이
    봐야 한다(ISSUE-002). 알림 채널이 따로 없어 구조화 로그로 낸다 —
    운영자가 `docker logs | grep WARNING`으로 잡는다(AGENTS.md 3단계).
    """
    if count <= threshold:
        return None
    return f"dead retryable jobs {count} exceeds threshold {threshold}"


def next_quota_reset(now: datetime, reset_utc_hour: int) -> datetime:
    """다음 쿼터 리셋 시각. Gemini 무료 티어는 07:00 UTC(태평양 자정) 기준이다."""
    candidate = now.replace(hour=reset_utc_hour, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


@dataclass(frozen=True, slots=True)
class Decision:
    """실패 후 잡을 어떻게 할지."""

    dead: bool
    run_at: datetime | None
    error_kind: ErrorKind
    consume_attempt: bool
    quota_wait_seconds: int = 0


class RetryPolicy:
    def __init__(self, settings: JobSettings, *, quota_reset_utc_hour: int = 7) -> None:
        self._settings = settings
        self._quota_reset_utc_hour = quota_reset_utc_hour

    def backoff_for(self, attempt: int) -> timedelta:
        """attempt는 1-base(첫 실패 후 1)."""
        table = self._settings.backoff_minutes
        minutes = table[min(attempt, len(table)) - 1] if table else 5
        return timedelta(minutes=minutes)

    def decide(
        self,
        exc: BaseException,
        *,
        attempt: int,
        max_attempt: int,
        quota_waited_seconds: int,
        now: datetime | None = None,
    ) -> Decision:
        now = now or utcnow()

        if isinstance(exc, PermanentError):
            return Decision(
                dead=True, run_at=None, error_kind=ErrorKind.PERMANENT, consume_attempt=True
            )

        if isinstance(exc, QuotaExceededError):
            reset = exc.reset_at or next_quota_reset(now, self._quota_reset_utc_hour)
            jitter = timedelta(seconds=random.randint(0, _JITTER_SECONDS))
            wait = max(int((reset - now).total_seconds()), 0)
            total_wait = quota_waited_seconds + wait
            if total_wait > self._settings.quota_max_wait_hours * 3600:
                # 며칠째 쿼터만 기다리는 잡은 사람이 봐야 한다.
                return Decision(
                    dead=True, run_at=None, error_kind=ErrorKind.QUOTA, consume_attempt=False
                )
            return Decision(
                dead=False,
                run_at=reset + jitter,
                error_kind=ErrorKind.QUOTA,
                consume_attempt=False,  # ← 쿼터는 재시도 횟수를 먹지 않는다
                quota_wait_seconds=wait,
            )

        # RetryableError와 미분류 예외는 같게 다룬다.
        if not isinstance(exc, RetryableError):
            pass
        if attempt >= max_attempt:
            return Decision(
                dead=True, run_at=None, error_kind=ErrorKind.RETRYABLE, consume_attempt=True
            )
        return Decision(
            dead=False,
            run_at=now + self.backoff_for(attempt),
            error_kind=ErrorKind.RETRYABLE,
            consume_attempt=True,
        )
