"""MongoDB 잡 큐 (ADR-0004). Kafka를 대체한다."""

from techletter.core.jobs.models import PRIORITY_BACKFILL, PRIORITY_NORMAL, Job
from techletter.core.jobs.policy import RetryPolicy
from techletter.core.jobs.queue import JobQueue
from techletter.core.jobs.runner import JobRunner
from techletter.core.jobs.types import COLLECTION, ErrorKind, JobStatus, JobType

__all__ = [
    "COLLECTION",
    "PRIORITY_BACKFILL",
    "PRIORITY_NORMAL",
    "ErrorKind",
    "Job",
    "JobQueue",
    "JobRunner",
    "JobStatus",
    "JobType",
    "RetryPolicy",
]
