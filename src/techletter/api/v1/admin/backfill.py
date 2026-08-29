"""백필 (04 §4.4).

요약이 안 된 포스트가 526건, 요약만 되고 임베딩이 안 된 것이 3건 쌓여 있는데
현행에는 되돌릴 방법이 없었다(ISSUE-001/008). 화면에서 건다.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import BackfillIn, BackfillStatusOut
from techletter.content.jobs import enqueue_embedding_requested, enqueue_summary_requested
from techletter.core.jobs.types import JobStatus, JobType
from techletter.core.logging import get_logger

router = APIRouter(prefix="/backfill", tags=["admin:backfill"])
logger = get_logger(__name__)


@router.get("/summary", response_model=BackfillStatusOut)
async def summary_status(ctx: Ctx, _: AdminUser) -> BackfillStatusOut:
    return BackfillStatusOut(
        unsummarized=len(await ctx.posts.find_unsummarized(10_000)),
        unembedded=len(await ctx.posts.find_summarized_not_embedded(10_000)),
        pending_jobs=await ctx.queue.count(
            status=JobStatus.PENDING.value, job_type=JobType.SUMMARY_REQUESTED.value
        ),
        dead_jobs=await ctx.queue.count(
            status=JobStatus.DEAD.value, job_type=JobType.SUMMARY_REQUESTED.value
        ),
    )


@router.post("/summary", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_summaries(ctx: Ctx, _: AdminUser, body: BackfillIn) -> dict[str, int]:
    """미요약 포스트를 오래된 것부터 큐에 넣는다.

    우선순위를 낮춰(숫자가 크다) 새로 수집된 글이 먼저 처리되게 한다.
    이미 대기 중인 잡은 중복 억제로 건너뛴다.
    """
    posts = await ctx.posts.find_unsummarized(body.limit)
    queued = [
        await enqueue_summary_requested(ctx.queue, post, priority=body.priority) for post in posts
    ]
    enqueued = sum(job is not None for job in queued)
    logger.info(
        "summary backfill enqueued",
        extra={"count": enqueued, "skipped": len(posts) - enqueued},
    )
    return {"enqueued": enqueued}


@router.post("/embeddings", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_embeddings(ctx: Ctx, _: AdminUser, body: BackfillIn) -> dict[str, int]:
    posts = await ctx.posts.find_summarized_not_embedded(body.limit)
    queued = [
        await enqueue_embedding_requested(ctx.queue, str(post.id), priority=body.priority)
        for post in posts
    ]
    enqueued = sum(job is not None for job in queued)
    logger.info("embedding backfill enqueued", extra={"count": enqueued})
    return {"enqueued": enqueued}
