"""Prometheus 텍스트 노출 형식의 잡 큐 지표(11.4).

`/health`처럼 `/api/v1` 밖에 두고 계약 문서에도 올리지 않는다 — Traefik이
`/api`만 라우팅하므로 외부에는 노출되지 않고, 도커 네트워크 안에서
`http://techletter_api:8080/metrics`로만 닿는다. 이 프로젝트에는 아직
Prometheus가 없다 — 나중에 붙이면 바로 스크레이프할 수 있도록 형식만
맞춰 둔다. `dead` 잡의 `retryable` 비율이 임계치를 넘는 알림은 워커의
`maintenance()` 루프가 구조화 로그로 낸다(`core/jobs/policy.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from techletter.core.jobs.types import ErrorKind

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    container = getattr(request.app.state, "container", None)
    if container is None:
        return Response(status_code=503, media_type="text/plain")

    stats = await container.queue.stats()
    dead_retryable = await container.queue.count_dead(ErrorKind.RETRYABLE)

    lines = [
        "# HELP techletter_jobs Job queue count by status.",
        "# TYPE techletter_jobs gauge",
    ]
    for job_status, count in sorted(stats["by_status"].items()):
        lines.append(f'techletter_jobs{{status="{job_status}"}} {count}')

    lines += [
        "# HELP techletter_jobs_by_type Pending/dead job count by type.",
        "# TYPE techletter_jobs_by_type gauge",
    ]
    for key, count in sorted(stats["by_type"].items()):
        job_type, job_status = key.rsplit(":", 1)
        lines.append(f'techletter_jobs_by_type{{type="{job_type}",status="{job_status}"}} {count}')

    lines += [
        "# HELP techletter_jobs_dead_retryable Dead jobs whose last failure was retryable"
        " (exhausted retries, not a permanent error) — these are worth investigating.",
        "# TYPE techletter_jobs_dead_retryable gauge",
        f"techletter_jobs_dead_retryable {dead_retryable}",
    ]

    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
