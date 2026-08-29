"""잡 러너 — 클레임 → 핸들러 → 상태 전이 루프.

현행 컨슈머의 문제(ISSUE-011, ISSUE-022)를 구조적으로 없앤다.
- `stop_flag: list[bool]` 폴링 대신 `asyncio.Event`
- 예외를 삼키지 않는다. 삼키면 재시도·DLQ가 통째로 무력화된다
  (현행 `chat_handler`가 그랬다).
- 종료 신호를 받으면 처리 중인 잡을 끝내고 나간다(drain).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Protocol

from techletter.core.jobs.types import JobStatus
from techletter.core.logging import bind_context, get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue
    from techletter.core.jobs.types import JobType
    from techletter.settings import JobSettings

__all__ = ["JobHandler", "JobRunner"]

logger = get_logger(__name__)


class JobHandler(Protocol):
    """잡 하나를 처리한다. 멱등해야 한다(크래시 후 재실행될 수 있다)."""

    async def __call__(self, job: Job) -> None: ...


class JobRunner:
    def __init__(
        self,
        queue: JobQueue,
        settings: JobSettings,
        handlers: dict[JobType, Callable[[Job], Awaitable[None]]],
        *,
        worker_id: str,
        on_tick: Callable[[], None] | None = None,
    ) -> None:
        self._queue = queue
        self._settings = settings
        self._handlers = handlers
        self._worker_id = worker_id
        self._on_tick = on_tick
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> bool:
        """잡 하나를 처리한다. 처리했으면 True, 큐가 비었으면 False."""
        job = await self._queue.claim(list(self._handlers), self._worker_id)
        if job is None:
            return False

        bind_context(job_id=str(job.id), trace_id=job.trace_id)
        handler = self._handlers.get(job.type)
        if handler is None:
            # 등록되지 않은 타입을 클레임했다 — 설정 오류다. 되돌려 놓는다.
            logger.error("no handler for job type", extra={"job_type": job.type.value})
            await self._queue.fail(job, RuntimeError(f"no handler for {job.type.value}"))
            return True

        logger.info(
            "job started",
            extra={"job_type": job.type.value, "job_key": job.key, "attempt": job.attempt},
        )
        try:
            await handler(job)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            status = await self._queue.fail(job, exc)
            if status is JobStatus.DEAD:
                logger.error("job dead", extra={"job_type": job.type.value}, exc_info=exc)
        else:
            await self._queue.complete(job)
            logger.info("job done", extra={"job_type": job.type.value, "job_key": job.key})
        finally:
            bind_context(job_id=None)
        return True

    async def run_forever(self) -> None:
        """종료 신호가 올 때까지 잡을 처리한다."""
        idle = self._settings.poll_interval_seconds
        logger.info("job runner started", extra={"worker_id": self._worker_id})
        while not self._stop.is_set():
            if self._on_tick:
                self._on_tick()
            try:
                worked = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # 큐 자체가 실패한 경우(예: Mongo 순단). 루프는 계속 돈다.
                logger.exception("job loop error")
                worked = False

            if worked:
                idle = self._settings.poll_interval_seconds
                continue
            # 큐가 비면 점진적으로 폴링 간격을 늘린다.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=idle)
            idle = min(idle * 1.5, self._settings.idle_backoff_seconds)
        logger.info("job runner stopped", extra={"worker_id": self._worker_id})
