"""MongoDB 잡 큐 (ADR-0004).

Kafka를 대체한다. 큐·상태·재시도·DLQ가 컬렉션 하나에 있어 `mongosh`나
어드민 화면에서 그대로 보인다.

핵심은 `find_one_and_update`로 하는 **원자적 클레임**이다. 워커를 여러 개
띄워도 잡 하나는 정확히 한 워커가 가져간다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.jobs.models import PRIORITY_NORMAL, Job
from techletter.core.jobs.types import COLLECTION, ErrorKind, JobStatus, JobType
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.core.jobs.policy import RetryPolicy
    from techletter.core.pagination import Page
    from techletter.settings import JobSettings

__all__ = ["JobQueue"]

logger = get_logger(__name__)

register_indexes(
    COLLECTION,
    [
        # 클레임 쿼리: {status, type} 동등 + {priority, run_at} 정렬
        IndexSpec(
            "idx_jobs_claim",
            [
                ("status", ASCENDING),
                ("type", ASCENDING),
                ("priority", ASCENDING),
                ("run_at", ASCENDING),
            ],
        ),
        # 스테일 락 회수
        IndexSpec("idx_jobs_stale", [("status", ASCENDING), ("locked_at", ASCENDING)]),
        # enqueue 중복 억제
        IndexSpec(
            "idx_jobs_dedupe",
            [("key", ASCENDING), ("type", ASCENDING), ("status", ASCENDING)],
        ),
        # 완료된 잡만 자동 정리한다. dead는 사람이 볼 때까지 남긴다.
        IndexSpec(
            "ttl_jobs_done",
            [("finished_at", ASCENDING)],
            expire_after_seconds=14 * 24 * 3600,
            partial_filter={"status": JobStatus.DONE.value},
        ),
    ],
)


class JobQueue:
    def __init__(self, db: AsyncDatabase, settings: JobSettings, policy: RetryPolicy) -> None:
        self._col = db[COLLECTION]
        self._settings = settings
        self._policy = policy

    # ── 발행 ────────────────────────────────────────────────────────
    async def enqueue(
        self,
        job_type: JobType,
        key: str,
        payload: dict[str, Any] | None = None,
        *,
        priority: int = PRIORITY_NORMAL,
        run_at: datetime | None = None,
        trace_id: str | None = None,
        dedupe: bool = True,
    ) -> Job | None:
        """잡을 넣는다. 이미 대기/실행 중인 같은 (key, type)이 있으면 건너뛴다.

        중복 억제는 RSS 재수집이나 어드민 연속 클릭을 막는다.
        건너뛰면 None을 준다.
        """
        if dedupe and await self._col.find_one(
            {
                "key": key,
                "type": job_type.value,
                "status": {"$in": [JobStatus.PENDING.value, JobStatus.RUNNING.value]},
            },
            projection={"_id": 1},
        ):
            logger.debug("job deduped", extra={"job_type": job_type.value, "job_key": key})
            return None

        job = Job(
            type=job_type,
            key=key,
            payload=payload or {},
            priority=priority,
            max_attempt=self._settings.max_attempt,
            run_at=run_at or utcnow(),
            trace_id=trace_id,
        )
        result = await self._col.insert_one(job.to_mongo())
        job.id = result.inserted_id
        logger.info(
            "job enqueued",
            extra={"job_id": str(job.id), "job_type": job_type.value, "job_key": key},
        )
        return job

    # ── 소비 ────────────────────────────────────────────────────────
    async def claim(self, types: list[JobType], worker_id: str) -> Job | None:
        """실행 가능한 잡 하나를 원자적으로 가져온다. 없으면 None."""
        now = utcnow()
        doc = await self._col.find_one_and_update(
            {
                "status": JobStatus.PENDING.value,
                "type": {"$in": [t.value for t in types]},
                "run_at": {"$lte": now},
            },
            {
                "$set": {
                    "status": JobStatus.RUNNING.value,
                    "locked_by": worker_id,
                    "locked_at": now,
                    "updated_at": now,
                },
                "$inc": {"attempt": 1},
            },
            sort=[("priority", ASCENDING), ("run_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        return Job.model_validate(doc) if doc else None

    async def complete(self, job: Job) -> None:
        now = utcnow()
        await self._col.update_one(
            {"_id": job.id},
            {
                "$set": {
                    "status": JobStatus.DONE.value,
                    "finished_at": now,
                    "updated_at": now,
                    "locked_by": None,
                    "locked_at": None,
                    "last_error": None,
                }
            },
        )

    async def fail(self, job: Job, exc: BaseException) -> JobStatus:
        """실패를 기록하고 재시도 예약 또는 dead 처리한다."""
        decision = self._policy.decide(
            exc,
            attempt=job.attempt,
            max_attempt=job.max_attempt,
            quota_waited_seconds=job.quota_waited_seconds,
        )
        now = utcnow()
        message = f"{type(exc).__name__}: {exc}"[:500]
        update: dict[str, Any] = {
            "last_error": message,
            "error_kind": decision.error_kind.value,
            "updated_at": now,
            "locked_by": None,
            "locked_at": None,
        }
        inc: dict[str, Any] = {}

        if decision.dead:
            update["status"] = JobStatus.DEAD.value
            update["finished_at"] = now
            new_status = JobStatus.DEAD
        else:
            update["status"] = JobStatus.PENDING.value
            update["run_at"] = decision.run_at
            new_status = JobStatus.PENDING

        if not decision.consume_attempt:
            # 쿼터 대기는 재시도 횟수를 소모하지 않는다. claim이 올린 값을 되돌린다.
            inc["attempt"] = -1
        if decision.quota_wait_seconds:
            inc["quota_waited_seconds"] = decision.quota_wait_seconds

        ops: dict[str, Any] = {"$set": update}
        if inc:
            ops["$inc"] = inc
        await self._col.update_one({"_id": job.id}, ops)

        logger.warning(
            "job failed",
            extra={
                "job_id": str(job.id),
                "job_type": job.type.value,
                "attempt": job.attempt,
                "error_kind": decision.error_kind.value,
                "next_status": new_status.value,
                "run_at": decision.run_at.isoformat() if decision.run_at else None,
            },
        )
        return new_status

    # ── 유지보수 ─────────────────────────────────────────────────────
    async def recover_stale(self, *, timeout_minutes: int | None = None) -> int:
        """워커가 죽어 running으로 남은 잡을 pending으로 되돌린다."""
        timeout = timeout_minutes or self._settings.lock_timeout_minutes
        cutoff = utcnow() - timedelta(minutes=timeout)
        result = await self._col.update_many(
            {"status": JobStatus.RUNNING.value, "locked_at": {"$lt": cutoff}},
            {
                "$set": {
                    "status": JobStatus.PENDING.value,
                    "locked_by": None,
                    "locked_at": None,
                    "updated_at": utcnow(),
                    "error_kind": ErrorKind.RETRYABLE.value,
                    "last_error": "worker lock expired",
                }
            },
        )
        if result.modified_count:
            logger.warning("stale jobs recovered", extra={"count": result.modified_count})
        return result.modified_count

    async def stats(self) -> dict[str, Any]:
        """운영 대시보드용 집계(04 §4.4 `/admin/jobs/stats`)."""
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        async for row in await self._col.aggregate(
            [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        ):
            by_status[row["_id"]] = row["n"]
        async for row in await self._col.aggregate(
            [
                {"$match": {"status": {"$in": [JobStatus.PENDING.value, JobStatus.DEAD.value]}}},
                {"$group": {"_id": {"type": "$type", "status": "$status"}, "n": {"$sum": 1}}},
            ]
        ):
            by_type[f"{row['_id']['type']}:{row['_id']['status']}"] = row["n"]
        oldest = await self._col.find_one(
            {"status": JobStatus.PENDING.value}, sort=[("run_at", ASCENDING)]
        )
        return {
            "by_status": by_status,
            "by_type": by_type,
            "oldest_pending_at": oldest.get("run_at") if oldest else None,
        }

    async def count_dead(self, error_kind: ErrorKind | None = None) -> int:
        """dead 잡 개수. `error_kind` 지정 시 그 성격만(11.4 알림·`/metrics`용)."""
        query: dict[str, Any] = {"status": JobStatus.DEAD.value}
        if error_kind is not None:
            query["error_kind"] = error_kind.value
        return await self._col.count_documents(query)

    async def list_jobs(
        self,
        page: Page,
        *,
        status: str | None = None,
        job_type: str | None = None,
    ) -> tuple[list[Job], int]:
        """어드민 잡 목록. 최근 갱신 순으로 준다."""
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if job_type:
            query["type"] = job_type
        total = await self._col.count_documents(query)
        cursor = (
            self._col.find(query)
            .sort([("updated_at", DESCENDING)])
            .skip(page.skip)
            .limit(page.page_size)
        )
        return [Job.model_validate(doc) async for doc in cursor], total

    async def retry_bulk(
        self, *, job_type: str | None = None, error_kind: str | None = None, limit: int = 100
    ) -> int:
        """dead 잡을 한 번에 되살린다. 실제로 되살린 개수를 준다.

        `update_many`를 한 번에 쓰지 않고 개수를 제한하는 이유: dead가 수천 건일
        때 통째로 풀면 워커가 같은 실패를 반복하며 큐를 채운다.
        """
        query: dict[str, Any] = {"status": JobStatus.DEAD.value}
        if job_type:
            query["type"] = job_type
        if error_kind:
            query["error_kind"] = error_kind
        ids = [
            doc["_id"]
            async for doc in self._col.find(query, projection={"_id": 1}).limit(max(1, limit))
        ]
        if not ids:
            return 0
        result = await self._col.update_many(
            {"_id": {"$in": ids}},
            {
                "$set": {
                    "status": JobStatus.PENDING.value,
                    "attempt": 0,
                    "quota_waited_seconds": 0,
                    "run_at": utcnow(),
                    "updated_at": utcnow(),
                    "finished_at": None,
                    "last_error": None,
                    "error_kind": None,
                }
            },
        )
        logger.info("jobs retried in bulk", extra={"count": result.modified_count})
        return result.modified_count

    async def delete(self, job_id: Any) -> bool:
        result = await self._col.delete_one({"_id": job_id})
        return result.deleted_count > 0

    async def count(self, *, status: str | None = None, job_type: str | None = None) -> int:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if job_type:
            query["type"] = job_type
        return await self._col.count_documents(query)

    async def retry(self, job_id: Any) -> Job | None:
        """dead 잡을 즉시 다시 큐에 넣는다(어드민/CLI)."""
        doc = await self._col.find_one_and_update(
            {"_id": job_id, "status": JobStatus.DEAD.value},
            {
                "$set": {
                    "status": JobStatus.PENDING.value,
                    "attempt": 0,
                    "quota_waited_seconds": 0,
                    "run_at": utcnow(),
                    "updated_at": utcnow(),
                    "finished_at": None,
                    "last_error": None,
                    "error_kind": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return Job.model_validate(doc) if doc else None
