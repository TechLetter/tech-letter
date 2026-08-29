"""잡 러너 — 핸들러 실행과 상태 전이, 종료 신호."""

from __future__ import annotations

import asyncio

import pytest

from techletter.core.errors import PermanentError, RetryableError
from techletter.core.jobs import JobRunner, JobStatus, JobType

pytestmark = pytest.mark.integration

SUMMARY = JobType.SUMMARY_REQUESTED


def make_runner(queue, job_settings, handler, *, on_tick=None) -> JobRunner:
    return JobRunner(
        queue, job_settings, {SUMMARY: handler}, worker_id="test-worker", on_tick=on_tick
    )


async def test_run_once_processes_and_completes(queue, job_settings, mongo_db):
    seen = []

    async def handler(job):
        seen.append(job.key)

    runner = make_runner(queue, job_settings, handler)
    await queue.enqueue(SUMMARY, "post-1", {"n": 1})

    assert await runner.run_once() is True
    assert seen == ["post-1"]
    doc = await mongo_db["jobs"].find_one({"key": "post-1"})
    assert doc["status"] == JobStatus.DONE.value


async def test_run_once_returns_false_when_queue_empty(queue, job_settings):
    async def handler(job):  # pragma: no cover - 호출되지 않는다
        raise AssertionError

    assert await make_runner(queue, job_settings, handler).run_once() is False


async def test_handler_exception_is_not_swallowed(queue, job_settings, mongo_db):
    """현행 chat_handler는 예외를 삼켜 재시도·DLQ가 통째로 죽어 있었다(ISSUE-011)."""

    async def handler(job):
        raise RetryableError("일시 오류")

    await queue.enqueue(SUMMARY, "post-1")
    assert await make_runner(queue, job_settings, handler).run_once() is True

    doc = await mongo_db["jobs"].find_one({"key": "post-1"})
    assert doc["status"] == JobStatus.PENDING.value
    assert doc["attempt"] == 1
    assert "일시 오류" in doc["last_error"]


async def test_permanent_failure_marks_dead(queue, job_settings, mongo_db):
    async def handler(job):
        raise PermanentError("요약 불가", reason="not_summarizable")

    await queue.enqueue(SUMMARY, "post-1")
    await make_runner(queue, job_settings, handler).run_once()

    doc = await mongo_db["jobs"].find_one({"key": "post-1"})
    assert doc["status"] == JobStatus.DEAD.value


async def test_unregistered_type_is_not_lost(queue, job_settings, mongo_db):
    """핸들러가 없는 타입을 잡으면 실패로 기록하고 잡을 잃지 않는다."""

    async def handler(job):  # pragma: no cover
        raise AssertionError

    runner = JobRunner(
        queue,
        job_settings,
        {SUMMARY: handler, JobType.EMBEDDING_REQUESTED: handler},
        worker_id="w",
    )
    # 핸들러 dict에는 있지만 실행 시점에 빼서 미등록 상황을 만든다
    runner._handlers.pop(JobType.EMBEDDING_REQUESTED)
    await queue.enqueue(JobType.EMBEDDING_REQUESTED, "post-1")

    # claim 대상에서도 빠지므로 아무것도 처리하지 않는다
    assert await runner.run_once() is False
    doc = await mongo_db["jobs"].find_one({"key": "post-1"})
    assert doc["status"] == JobStatus.PENDING.value


async def test_run_forever_stops_on_request(queue, job_settings):
    processed = asyncio.Event()

    async def handler(job):
        processed.set()

    runner = make_runner(queue, job_settings, handler)
    await queue.enqueue(SUMMARY, "post-1")

    task = asyncio.create_task(runner.run_forever())
    await asyncio.wait_for(processed.wait(), timeout=5)
    runner.request_stop()
    await asyncio.wait_for(task, timeout=5)
    assert task.done()


async def test_run_forever_survives_handler_errors(queue, job_settings, mongo_db):
    """한 잡이 실패해도 루프는 다음 잡을 계속 처리한다."""
    done = asyncio.Event()

    async def handler(job):
        if job.key == "bad":
            raise RetryableError("실패")
        done.set()

    runner = make_runner(queue, job_settings, handler)
    await queue.enqueue(SUMMARY, "bad")
    await queue.enqueue(SUMMARY, "good")

    task = asyncio.create_task(runner.run_forever())
    await asyncio.wait_for(done.wait(), timeout=5)
    runner.request_stop()
    await asyncio.wait_for(task, timeout=5)

    assert (await mongo_db["jobs"].find_one({"key": "good"}))["status"] == JobStatus.DONE.value
    assert (await mongo_db["jobs"].find_one({"key": "bad"}))["status"] == JobStatus.PENDING.value


async def test_on_tick_is_called(queue, job_settings):
    ticks = []

    async def handler(job):
        pass

    runner = make_runner(queue, job_settings, handler, on_tick=lambda: ticks.append(1))
    task = asyncio.create_task(runner.run_forever())
    await asyncio.sleep(0.05)
    runner.request_stop()
    await asyncio.wait_for(task, timeout=5)
    assert ticks, "heartbeat 훅이 호출되어야 한다"
