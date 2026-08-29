"""잡 문서 모델 (ADR-0004 §1)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from techletter.core.db.documents import BaseDocument, MongoDateTime
from techletter.core.jobs.types import ErrorKind, JobStatus, JobType
from techletter.core.time import utcnow

__all__ = ["PRIORITY_BACKFILL", "PRIORITY_NORMAL", "Job"]

PRIORITY_NORMAL = 0
"""신규 포스트 등 평상시 작업. 낮을수록 먼저 처리된다."""

PRIORITY_BACKFILL = 10
"""백필. 신규 작업이 항상 앞선다(ADR-0004 §7)."""


class Job(BaseDocument):
    type: JobType
    key: str
    """중복 억제·추적용 도메인 키(post_id, session_id 등)."""

    payload: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    priority: int = PRIORITY_NORMAL

    attempt: int = 0
    max_attempt: int = 5

    run_at: MongoDateTime = Field(default_factory=utcnow)
    """이 시각 이후에 실행 가능하다. 지연 재시도를 여기서 표현한다."""

    locked_by: str | None = None
    locked_at: MongoDateTime | None = None

    last_error: str | None = None
    error_kind: ErrorKind | None = None
    quota_waited_seconds: int = 0
    """쿼터 대기 누적. `quota_max_wait_hours`를 넘으면 dead로 보낸다."""

    trace_id: str | None = None
    finished_at: MongoDateTime | None = None
