"""잡 큐 — 실제 MongoDB로 검증한다 (ADR-0004).

Kafka를 대체하는 핵심이라 동시성·재시도·회수를 실제 DB에서 확인한다.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from techletter.core.errors import PermanentError, QuotaExceededError, RetryableError
from techletter.core.jobs import (
    PRIORITY_BACKFILL,
    PRIORITY_NORMAL,
    ErrorKind,
    JobStatus,
    JobType,
)
from techletter.core.time import utcnow

pytestmark = pytest.mark.integration

SUMMARY = JobType.SUMMARY_REQUESTED


async def test_enqueue_and_claim(queue):
    job = await queue.enqueue(SUMMARY, "post-1", {"title": "테스트"})
    assert job is not None
    assert job.status is JobStatus.PENDING
    assert job.attempt == 0

    claimed = await queue.claim([SUMMARY], "worker-1")
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status is JobStatus.RUNNING
    assert claimed.attempt == 1
    assert claimed.locked_by == "worker-1"
    assert claimed.payload["title"] == "테스트"


async def test_claim_returns_none_when_empty(queue):
    assert await queue.claim([SUMMARY], "worker-1") is None


async def test_claim_ignores_future_run_at(queue):
    await queue.enqueue(SUMMARY, "post-1", run_at=utcnow() + timedelta(hours=1))
    assert await queue.claim([SUMMARY], "worker-1") is None


async def test_enqueue_dedupes_pending_job(queue):
    first = await queue.enqueue(SUMMARY, "post-1")
    second = await queue.enqueue(SUMMARY, "post-1")
    assert first is not None
    assert second is None, "같은 key/type이 대기 중이면 중복 발행하지 않는다"


async def test_enqueue_dedupe_can_be_disabled(queue):
    await queue.enqueue(SUMMARY, "post-1")
    assert await queue.enqueue(SUMMARY, "post-1", dedupe=False) is not None


async def test_enqueue_after_completion_is_allowed(queue):
    job = await queue.enqueue(SUMMARY, "post-1")
    claimed = await queue.claim([SUMMARY], "w1")
    await queue.complete(claimed)
    assert await queue.enqueue(SUMMARY, "post-1") is not None, "완료된 뒤에는 다시 넣을 수 있다"
    assert job is not None


async def test_concurrent_claims_have_exactly_one_winner(queue):
    """워커를 여러 개 띄워도 잡 하나는 한 번만 처리된다."""
    await queue.enqueue(SUMMARY, "post-1")
    results = await asyncio.gather(*(queue.claim([SUMMARY], f"w{i}") for i in range(20)))
    winners = [r for r in results if r is not None]
    assert len(winners) == 1


async def test_many_jobs_are_distributed_without_duplication(queue):
    for i in range(30):
        await queue.enqueue(SUMMARY, f"post-{i}")
    results = await asyncio.gather(*(queue.claim([SUMMARY], f"w{i % 3}") for i in range(30)))
    claimed_ids = [r.id for r in results if r is not None]
    assert len(claimed_ids) == 30
    assert len(set(claimed_ids)) == 30, "같은 잡을 두 워커가 가져가면 안 된다"


async def test_priority_orders_claims(queue):
    """신규(priority 0)가 백필(10)보다 항상 먼저 처리된다 (ADR-0004 §7)."""
    await queue.enqueue(SUMMARY, "backfill", priority=PRIORITY_BACKFILL)
    await queue.enqueue(SUMMARY, "fresh", priority=PRIORITY_NORMAL)
    first = await queue.claim([SUMMARY], "w1")
    second = await queue.claim([SUMMARY], "w1")
    assert first is not None
    assert second is not None
    assert first.key == "fresh"
    assert second.key == "backfill"


async def test_claim_filters_by_type(queue):
    await queue.enqueue(JobType.EMBEDDING_REQUESTED, "post-1")
    assert await queue.claim([SUMMARY], "w1") is None
    assert await queue.claim([JobType.EMBEDDING_REQUESTED], "w1") is not None


async def test_complete_marks_done(queue, mongo_db):
    await queue.enqueue(SUMMARY, "post-1")
    job = await queue.claim([SUMMARY], "w1")
    await queue.complete(job)

    doc = await mongo_db["jobs"].find_one({"_id": job.id})
    assert doc["status"] == JobStatus.DONE.value
    assert doc["finished_at"] is not None
    assert doc["locked_by"] is None


async def test_retryable_failure_reschedules(queue, mongo_db):
    await queue.enqueue(SUMMARY, "post-1")
    job = await queue.claim([SUMMARY], "w1")
    status = await queue.fail(job, RetryableError("일시 오류"))

    assert status is JobStatus.PENDING
    doc = await mongo_db["jobs"].find_one({"_id": job.id})
    assert doc["attempt"] == 1
    assert doc["error_kind"] == ErrorKind.RETRYABLE.value
    assert doc["run_at"] > utcnow(), "백오프만큼 미래로 밀린다"
    assert await queue.claim([SUMMARY], "w1") is None, "재시도 시각 전에는 안 잡힌다"


async def test_permanent_failure_goes_dead(queue, mongo_db):
    await queue.enqueue(SUMMARY, "post-1")
    job = await queue.claim([SUMMARY], "w1")
    status = await queue.fail(job, PermanentError("봇 차단", reason="bot_blocked"))

    assert status is JobStatus.DEAD
    doc = await mongo_db["jobs"].find_one({"_id": job.id})
    assert doc["status"] == JobStatus.DEAD.value
    assert doc["error_kind"] == ErrorKind.PERMANENT.value
    assert "봇 차단" in doc["last_error"]


async def test_quota_failure_does_not_consume_attempt(queue, mongo_db):
    """ISSUE-001: 쿼터 실패가 재시도 횟수를 먹으면 안 된다."""
    await queue.enqueue(SUMMARY, "post-1")
    job = await queue.claim([SUMMARY], "w1")
    assert job.attempt == 1

    await queue.fail(job, QuotaExceededError("일일 한도 20회 소진"))

    doc = await mongo_db["jobs"].find_one({"_id": job.id})
    assert doc["attempt"] == 0, "claim이 올린 attempt를 되돌린다"
    assert doc["error_kind"] == ErrorKind.QUOTA.value
    assert doc["status"] == JobStatus.PENDING.value
    assert doc["quota_waited_seconds"] > 0


async def test_job_dies_after_max_attempts(queue, mongo_db):
    enqueued = await queue.enqueue(SUMMARY, "post-1")
    assert enqueued is not None
    for _ in range(5):
        job = await queue.claim([SUMMARY], "w1")
        assert job is not None
        await queue.fail(job, RetryableError("계속 실패"))
        # 다음 시도를 위해 백오프를 지운다
        await mongo_db["jobs"].update_one({"_id": enqueued.id}, {"$set": {"run_at": utcnow()}})

    doc = await mongo_db["jobs"].find_one({"_id": enqueued.id})
    assert doc["status"] == JobStatus.DEAD.value
    assert doc["attempt"] == 5


async def test_recover_stale_locks(queue, mongo_db):
    """워커가 죽어 running으로 남은 잡을 되살린다."""
    await queue.enqueue(SUMMARY, "post-1")
    job = await queue.claim([SUMMARY], "dead-worker")
    await mongo_db["jobs"].update_one(
        {"_id": job.id}, {"$set": {"locked_at": utcnow() - timedelta(hours=2)}}
    )

    recovered = await queue.recover_stale(timeout_minutes=30)
    assert recovered == 1
    assert await queue.claim([SUMMARY], "w2") is not None


async def test_recover_stale_leaves_fresh_locks(queue):
    await queue.enqueue(SUMMARY, "post-1")
    await queue.claim([SUMMARY], "busy-worker")
    assert await queue.recover_stale(timeout_minutes=30) == 0


async def test_retry_revives_dead_job(queue):
    await queue.enqueue(SUMMARY, "post-1")
    job = await queue.claim([SUMMARY], "w1")
    await queue.fail(job, PermanentError("영구 실패"))

    revived = await queue.retry(job.id)
    assert revived is not None
    assert revived.status is JobStatus.PENDING
    assert revived.attempt == 0
    assert await queue.claim([SUMMARY], "w1") is not None


async def test_retry_ignores_non_dead_job(queue):
    job = await queue.enqueue(SUMMARY, "post-1")
    assert await queue.retry(job.id) is None


async def test_stats(queue):
    await queue.enqueue(SUMMARY, "a")
    await queue.enqueue(SUMMARY, "b")
    job = await queue.claim([SUMMARY], "w1")
    await queue.fail(job, PermanentError("실패"))

    stats = await queue.stats()
    assert stats["by_status"][JobStatus.DEAD.value] == 1
    assert stats["by_status"][JobStatus.PENDING.value] == 1
    assert stats["oldest_pending_at"] is not None
