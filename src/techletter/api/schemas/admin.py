"""운영 대시보드 DTO."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from techletter.core.time import to_iso_z

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.jobs.models import Job

__all__ = [
    "BackfillIn",
    "BackfillStatusOut",
    "BlogIn",
    "JobOut",
    "JobStatsOut",
    "LlmModelStatOut",
    "PostIn",
    "RetryBulkIn",
]


class JobOut(BaseModel):
    id: str
    type: str
    key: str
    status: str
    attempt: int
    max_attempt: int
    priority: int
    run_at: str | None
    last_error: str | None
    error_kind: str | None
    trace_id: str | None
    created_at: str | None
    updated_at: str | None
    finished_at: str | None

    @classmethod
    def of(cls, job: Job) -> JobOut:
        return cls(
            id=str(job.id),
            type=job.type.value,
            key=job.key,
            status=job.status.value,
            attempt=job.attempt,
            max_attempt=job.max_attempt,
            priority=job.priority,
            run_at=to_iso_z(job.run_at),
            last_error=job.last_error,
            error_kind=job.error_kind.value if job.error_kind else None,
            trace_id=job.trace_id,
            created_at=to_iso_z(job.created_at),
            updated_at=to_iso_z(job.updated_at),
            finished_at=to_iso_z(job.finished_at),
        )
        # payload 는 내보내지 않는다 — 요약 결과 본문이 수십 KB다.


class JobStatsOut(BaseModel):
    by_status: dict[str, int]
    by_type: dict[str, int]
    oldest_pending_at: str | None


class LlmModelStatOut(BaseModel):
    model_id: str
    purpose: str
    attempts: int
    successes: int
    json_failures: int
    rate_limited: int
    success_rate: float
    avg_latency_ms: float
    healthy: bool | None = None
    uptime_24h: float | None = None
    last_used_at: str | None = None
    last_error: str | None = None

    @classmethod
    def of(cls, row: dict[str, Any], health: dict[str, Any] | None = None) -> LlmModelStatOut:
        attempts = int(row.get("attempts") or 0)
        successes = int(row.get("successes") or 0)
        return cls(
            model_id=str(row.get("model_id") or ""),
            purpose=str(row.get("purpose") or ""),
            attempts=attempts,
            successes=successes,
            json_failures=int(row.get("json_failures") or 0),
            rate_limited=int(row.get("rate_limited") or 0),
            success_rate=round(successes / attempts, 4) if attempts else 1.0,
            avg_latency_ms=round(float(row.get("avg_latency_ms") or 0.0), 1),
            healthy=health.get("healthy") if health else None,
            uptime_24h=health.get("uptime_24h") if health else None,
            last_used_at=to_iso_z(row.get("last_used_at")),
            last_error=row.get("last_error"),
        )


class RetryBulkIn(BaseModel):
    type: str | None = None
    error_kind: str | None = None
    limit: int = Field(default=100, gt=0, le=1000)


class BackfillStatusOut(BaseModel):
    unsummarized: int
    unembedded: int
    pending_jobs: int
    dead_jobs: int


class BackfillIn(BaseModel):
    limit: int = Field(default=50, gt=0, le=1000)
    # 백필은 신규 수집보다 뒤로 미룬다(숫자가 클수록 나중).
    priority: int = Field(default=10, ge=0, le=100)


class PostIn(BaseModel):
    blog_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    link: str = Field(min_length=1, max_length=2000)


class BlogIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    rss_url: str = Field(min_length=1, max_length=2000)
    blog_type: str = "company"
    is_active: bool = True
    tls_insecure: bool = False
