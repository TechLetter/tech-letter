"""어드민 포스트 (04 §4.4)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import AdminPostOut, JobAccepted, Paged, PostIn
from techletter.api.schemas.query import StrQ, parse_page
from techletter.content.models import ListPostsFilter
from techletter.core.jobs.types import JobType
from techletter.core.pagination import lenient_bool

router = APIRouter(prefix="/posts", tags=["admin:posts"])


@router.get("", response_model=Paged[AdminPostOut])
async def list_posts(
    ctx: Ctx,
    _: AdminUser,
    page: StrQ = None,
    page_size: StrQ = None,
    summarized: StrQ = None,
    embedded: StrQ = None,
    blog_id: StrQ = None,
    q: StrQ = None,
) -> Paged[AdminPostOut]:
    paging = parse_page(page, page_size)
    found, total = await ctx.posts.list_posts(
        ListPostsFilter(
            blog_id=(blog_id or "").strip() or None,
            summarized=lenient_bool(summarized),
            embedded=lenient_bool(embedded),
            search=(q or "").strip() or None,
        ),
        paging,
    )
    return Paged.of_page([AdminPostOut.of(post) for post in found], total, paging)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AdminPostOut)
async def create_post(ctx: Ctx, _: AdminUser, body: PostIn) -> AdminPostOut:
    post = await ctx.post_service.create(title=body.title, link=body.link, blog_id=body.blog_id)
    return AdminPostOut.of(post)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(ctx: Ctx, _: AdminUser, post_id: str) -> Response:
    await ctx.post_service.delete(post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{post_id}/summarize", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted
)
async def summarize(ctx: Ctx, _: AdminUser, post_id: str) -> JobAccepted:
    """요약을 다시 요청한다. 이미 대기 중이면 새 잡을 만들지 않는다."""
    await ctx.post_service.retry_summary(post_id)
    return JobAccepted(job_id=await _job_id(ctx, JobType.SUMMARY_REQUESTED, post_id))


@router.post("/{post_id}/embed", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
async def embed(ctx: Ctx, _: AdminUser, post_id: str) -> JobAccepted:
    await ctx.post_service.retry_embedding(post_id)
    return JobAccepted(job_id=await _job_id(ctx, JobType.EMBEDDING_REQUESTED, post_id))


async def _job_id(ctx: Ctx, job_type: JobType, key: str) -> str | None:
    """방금 걸린(또는 이미 있던) 잡의 id. 어드민이 상태를 추적할 수 있게 한다."""
    doc = await ctx.db["jobs"].find_one(
        {"key": key, "type": job_type.value, "status": {"$in": ["pending", "running"]}},
        projection={"_id": 1},
    )
    return str(doc["_id"]) if doc else None
