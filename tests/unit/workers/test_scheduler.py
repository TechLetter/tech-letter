"""주기 작업 스케줄러 — 첫 실행 시점."""

from __future__ import annotations

import pytest

from techletter.workers.scheduler import PeriodicTask, Scheduler


async def _noop() -> None:
    return None


def _delay(value: float):
    async def first_delay() -> float:
        return value

    return first_delay


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (PeriodicTask("a", 1800, _noop), 1800),  # 기본: 한 주기 미룸
        (PeriodicTask("b", 1800, _noop, run_at_start=True), 0),
        # 마지막 수집에서 10분 지났으면 20분만 기다린다
        (PeriodicTask("c", 1800, _noop, first_delay=_delay(1200)), 1200),
        # 이미 한 주기가 지났으면(음수) 바로
        (PeriodicTask("d", 1800, _noop, first_delay=_delay(-500)), 0),
        # 계산이 한 주기보다 길어도 한 주기까지만
        (PeriodicTask("e", 1800, _noop, first_delay=_delay(99999)), 1800),
    ],
)
async def test_the_first_run_waits_only_the_remaining_time(task, expected) -> None:
    assert await Scheduler([task])._first_delay(task) == expected


async def test_a_failing_lookup_falls_back_to_the_default() -> None:
    async def broken() -> float:
        raise RuntimeError("db down")

    task = PeriodicTask("f", 1800, _noop, first_delay=broken)

    assert await Scheduler([task])._first_delay(task) == 1800
