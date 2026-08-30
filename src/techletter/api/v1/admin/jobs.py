"""잡 큐 운영. 화면에서 상태를 보고 버튼으로 되살린다."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import JobOut, JobStatsOut, Paged, RetryBulkIn
from techletter.api.schemas.query import StrQ, parse_page
from techletter.core.errors import ResourceNotFoundError
from techletter.core.ids import to_object_id
from techletter.core.time import to_iso_z

router = APIRouter(prefix="/jobs", tags=["admin:jobs"])


# 쿼리 이름은 `status`, `type`이다. 파이썬 쪽에서는 그 이름이
# `fastapi.status`와 겹치므로 alias로 받는다.
StatusQ = Annotated[str | None, Query(alias="status")]
TypeQ = Annotated[str | None, Query(alias="type")]


@router.get("", response_model=Paged[JobOut])
async def list_jobs(
    ctx: Ctx,
    _: AdminUser,
    page: StrQ = None,
    page_size: StrQ = None,
    job_status: StatusQ = None,
    job_type: TypeQ = None,
) -> Paged[JobOut]:
    paging = parse_page(page, page_size, default_size=50)
    jobs, total = await ctx.queue.list_jobs(
        paging,
        status=(job_status or "").strip() or None,
        job_type=(job_type or "").strip() or None,
    )
    return Paged.of_page([JobOut.of(job) for job in jobs], total, paging)


@router.get("/stats", response_model=JobStatsOut)
async def job_stats(ctx: Ctx, _: AdminUser) -> JobStatsOut:
    raw = await ctx.queue.stats()
    return JobStatsOut(
        by_status=raw["by_status"],
        by_type=raw["by_type"],
        oldest_pending_at=to_iso_z(raw["oldest_pending_at"]),
    )


@router.post("/{job_id}/retry", response_model=JobOut)
async def retry_job(ctx: Ctx, _: AdminUser, job_id: str) -> JobOut:
    oid = to_object_id(job_id)
    job = await ctx.queue.retry(oid) if oid else None
    if job is None:
        # 없거나 dead가 아니다. 둘 다 "되살릴 게 없다"는 뜻이다.
        raise ResourceNotFoundError(f"재시도할 dead 잡이 없습니다: {job_id}")
    return JobOut.of(job)


@router.post("/retry-bulk")
async def retry_bulk(ctx: Ctx, _: AdminUser, body: RetryBulkIn) -> dict[str, int]:
    retried = await ctx.queue.retry_bulk(
        job_type=body.type, error_kind=body.error_kind, limit=body.limit
    )
    return {"retried": retried}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(ctx: Ctx, _: AdminUser, job_id: str) -> Response:
    oid = to_object_id(job_id)
    if oid is None or not await ctx.queue.delete(oid):
        raise ResourceNotFoundError(f"job not found: {job_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
