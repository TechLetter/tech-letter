"""주기 작업.

Kafka 시절에는 별도 스케줄러 스레드가 RSS를 돌렸고 재시도 워커가 따로
있었다. 이제는 core-worker 안에서 같은 이벤트 루프가 처리한다.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

__all__ = ["PeriodicTask", "Scheduler"]

logger = get_logger(__name__)


@dataclass(slots=True)
class PeriodicTask:
    name: str
    interval_seconds: float
    run: Callable[[], Awaitable[None]]
    run_at_start: bool = False
    """부팅 직후에도 한 번 돌릴지. RSS는 그러지 않는다(배포마다 수집이 돈다)."""


class Scheduler:
    """작업들을 각자의 주기로 돌린다. 하나가 실패해도 나머지는 계속 돈다."""

    def __init__(self, tasks: list[PeriodicTask]) -> None:
        self._tasks = tasks
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if not self._tasks:
            await self._stop.wait()
            return
        runners = [asyncio.create_task(self._loop(task)) for task in self._tasks]
        try:
            await self._stop.wait()
        finally:
            for runner in runners:
                runner.cancel()
            for runner in runners:
                with contextlib.suppress(asyncio.CancelledError):
                    await runner

    async def _loop(self, task: PeriodicTask) -> None:
        if not task.run_at_start:
            # 첫 실행을 한 주기 미룬다. 안 그러면 재배포할 때마다 수집이 돈다.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=task.interval_seconds)

        while not self._stop.is_set():
            started = asyncio.get_running_loop().time()
            try:
                await task.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                # 주기 작업 하나의 실패로 스케줄러가 죽으면 안 된다.
                logger.exception("periodic task failed", extra={"task": task.name})

            elapsed = asyncio.get_running_loop().time() - started
            # 작업이 주기보다 오래 걸려도 곧바로 다시 시작하지 않게 최소 1초는 쉰다.
            delay = max(1.0, task.interval_seconds - elapsed)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
