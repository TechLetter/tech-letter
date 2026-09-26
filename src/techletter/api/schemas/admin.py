"""운영 대시보드 DTO."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    created_at: str | None
    updated_at: str | None
    finished_at: str | None
    title: str | None
    """잡이 다루는 글의 제목·블로그. 실패 목록에서 행을 구분하려고 페이로드에서 이것만 꺼낸다."""
    blog_name: str | None

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
            created_at=to_iso_z(job.created_at),
            updated_at=to_iso_z(job.updated_at),
            finished_at=to_iso_z(job.finished_at),
            title=_text(job.payload.get("title")),
            blog_name=_text(job.payload.get("blog_name")),
        )
        # payload 는 내보내지 않는다 — 요약 결과 본문이 수십 KB다.


class JobStatsOut(BaseModel):
    by_status: dict[str, int]
    by_type: dict[str, int]
    oldest_pending_at: str | None


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
    is_active: bool = True


class BlogIconRefreshIn(BaseModel):
    site_url: str | None = Field(default=None, max_length=2000, pattern=r"^https?://\S+$")


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
