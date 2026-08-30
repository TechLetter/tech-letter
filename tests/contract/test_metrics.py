"""`/metrics` — Prometheus 텍스트 노출 형식(11.4). 계약 문서(04)의 대상이 아니다."""

from __future__ import annotations

import pytest

from techletter.core.jobs.types import JobType

pytestmark = pytest.mark.integration


async def test_metrics_is_unavailable_before_the_container_is_ready(client) -> None:
    """`app` 픽스처가 lifespan을 열어 두므로 여기선 항상 준비된 상태다.

    준비 전 동작은 단위 테스트(`test_app.py`)의 `/health` 케이스와 동일한
    가드(`container is None`)를 함께 쓴다 — 별도로 재확인하지 않는다.
    """
    response = await client.get("/metrics")
    assert response.status_code == 200


async def test_metrics_reports_job_counts(client, ctx) -> None:
    job = await ctx.queue.enqueue(JobType.SUMMARY_REQUESTED, "post-1", {"post_id": "p"})
    assert job is not None
    await ctx.db["jobs"].update_one(
        {"_id": job.id},
        {"$set": {"status": "dead", "last_error": "boom", "error_kind": "retryable"}},
    )

    response = await client.get("/metrics")
    body = response.text

    assert response.headers["content-type"].startswith("text/plain")
    assert 'techletter_jobs{status="dead"} 1' in body
    assert (
        f'techletter_jobs_by_type{{type="{JobType.SUMMARY_REQUESTED.value}",status="dead"}} 1'
        in body
    )
    assert "techletter_jobs_dead_retryable 1" in body
