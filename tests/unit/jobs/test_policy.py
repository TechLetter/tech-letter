"""재시도 정책 — ISSUE-001의 구조적 원인을 막는 규칙들.

현행: 재시도 창 1h46m < 일일 쿼터 리셋 24h → 쿼터 실패는 100% DLQ.
새 정책: 쿼터는 리셋 시각까지 대기하고 재시도 횟수를 소모하지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from techletter.core.errors import PermanentError, QuotaExceededError, RetryableError
from techletter.core.jobs.policy import RetryPolicy, next_quota_reset
from techletter.core.jobs.types import ErrorKind
from techletter.settings import JobSettings


@pytest.fixture
def policy() -> RetryPolicy:
    return RetryPolicy(JobSettings(), quota_reset_utc_hour=7)


NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


def test_backoff_table(policy):
    # 5m, 30m, 2h, 8h, 24h
    assert policy.backoff_for(1) == timedelta(minutes=5)
    assert policy.backoff_for(2) == timedelta(minutes=30)
    assert policy.backoff_for(3) == timedelta(hours=2)
    assert policy.backoff_for(4) == timedelta(hours=8)
    assert policy.backoff_for(5) == timedelta(hours=24)


def test_backoff_saturates_beyond_table(policy):
    assert policy.backoff_for(99) == timedelta(hours=24)


def test_total_backoff_window_exceeds_quota_reset(policy):
    """전체 재시도 창이 24시간을 넘어야 쿼터 리셋을 건널 수 있다."""
    total = sum((policy.backoff_for(i) for i in range(1, 6)), timedelta())
    assert total > timedelta(hours=24)


@pytest.mark.parametrize("hour", [0, 7, 23])
def test_next_quota_reset_is_in_future(hour):
    reset = next_quota_reset(NOW, hour)
    assert reset > NOW
    assert reset.hour == hour


def test_next_quota_reset_same_day_when_later(policy):
    reset = next_quota_reset(datetime(2026, 8, 29, 3, 0, tzinfo=UTC), 7)
    assert reset == datetime(2026, 8, 29, 7, 0, tzinfo=UTC)


def test_next_quota_reset_next_day_when_passed(policy):
    reset = next_quota_reset(datetime(2026, 8, 29, 9, 0, tzinfo=UTC), 7)
    assert reset == datetime(2026, 8, 30, 7, 0, tzinfo=UTC)


def test_retryable_schedules_backoff(policy):
    d = policy.decide(
        RetryableError("일시 오류"), attempt=1, max_attempt=5, quota_waited_seconds=0, now=NOW
    )
    assert d.dead is False
    assert d.error_kind is ErrorKind.RETRYABLE
    assert d.consume_attempt is True
    assert d.run_at == NOW + timedelta(minutes=5)


def test_unclassified_exception_is_treated_as_retryable(policy):
    d = policy.decide(
        ValueError("예상 못 한 오류"), attempt=1, max_attempt=5, quota_waited_seconds=0, now=NOW
    )
    assert d.dead is False
    assert d.error_kind is ErrorKind.RETRYABLE


def test_retryable_dies_after_max_attempt(policy):
    d = policy.decide(
        RetryableError("계속 실패"), attempt=5, max_attempt=5, quota_waited_seconds=0, now=NOW
    )
    assert d.dead is True
    assert d.error_kind is ErrorKind.RETRYABLE


def test_permanent_dies_immediately(policy):
    d = policy.decide(
        PermanentError("봇 차단", reason="bot_blocked"),
        attempt=1,
        max_attempt=5,
        quota_waited_seconds=0,
        now=NOW,
    )
    assert d.dead is True
    assert d.error_kind is ErrorKind.PERMANENT
    assert d.run_at is None


def test_quota_waits_until_reset_without_consuming_attempt(policy):
    """ISSUE-001의 핵심 수정."""
    d = policy.decide(
        QuotaExceededError("일일 한도"), attempt=1, max_attempt=5, quota_waited_seconds=0, now=NOW
    )
    assert d.dead is False
    assert d.consume_attempt is False  # ← 재시도 횟수를 먹지 않는다
    assert d.error_kind is ErrorKind.QUOTA
    assert d.run_at is not None
    # 다음 리셋(익일 07:00 UTC) 이후, jitter 2분 이내
    reset = datetime(2026, 8, 30, 7, 0, tzinfo=UTC)
    assert reset <= d.run_at <= reset + timedelta(seconds=120)


def test_quota_respects_explicit_reset_at(policy):
    explicit = NOW + timedelta(hours=3)
    d = policy.decide(
        QuotaExceededError("한도", reset_at=explicit),
        attempt=1,
        max_attempt=5,
        quota_waited_seconds=0,
        now=NOW,
    )
    assert d.run_at is not None
    assert explicit <= d.run_at <= explicit + timedelta(seconds=120)


def test_quota_gives_up_after_max_total_wait(policy):
    """며칠째 쿼터만 기다리는 잡은 사람이 봐야 한다."""
    d = policy.decide(
        QuotaExceededError("한도"),
        attempt=1,
        max_attempt=5,
        quota_waited_seconds=30 * 3600,  # 이미 30시간 대기
        now=NOW,
    )
    assert d.dead is True
    assert d.error_kind is ErrorKind.QUOTA
