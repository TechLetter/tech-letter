"""잡 타입·상태 정의 (ADR-0004)."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["COLLECTION", "ErrorKind", "JobStatus", "JobType"]

COLLECTION = "jobs"


class JobType(StrEnum):
    """잡 종류. Kafka 토픽 6개를 대체한다."""

    SUMMARY_REQUESTED = "summary.requested"
    SUMMARY_COMPLETED = "summary.completed"
    EMBEDDING_REQUESTED = "embedding.requested"
    EMBEDDING_COMPLETED = "embedding.completed"
    EMBEDDING_DELETE_REQUESTED = "embedding.delete_requested"
    CHAT_COMPRESSION_REQUESTED = "chat.compression_requested"


class JobStatus(StrEnum):
    """잡 상태.

    재시도 대기는 별도 상태가 아니라 `pending` + 미래의 `run_at`으로 표현한다.
    (`attempt > 0`이면 재시도 대기 중이라는 뜻이다.)
    `dead`가 곧 DLQ다 — 별도 컬렉션도 토픽도 두지 않는다.
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    DEAD = "dead"


class ErrorKind(StrEnum):
    """마지막 실패의 성격. 운영 대시보드에서 원인 분류에 쓴다."""

    RETRYABLE = "retryable"
    PERMANENT = "permanent"
    QUOTA = "quota"
