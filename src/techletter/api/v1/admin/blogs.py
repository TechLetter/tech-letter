"""어드민 블로그."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, status

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import AdminBlogOut, BlogIn, Paged
from techletter.api.schemas.query import StrQ, parse_page
from techletter.core.pagination import lenient_bool

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.models import Blog

router = APIRouter(prefix="/blogs", tags=["admin:blogs"])


@router.get("", response_model=Paged[AdminBlogOut])
async def list_blogs(
    ctx: Ctx,
    _: AdminUser,
    page: StrQ = None,
    page_size: StrQ = None,
    is_active: StrQ = None,
) -> Paged[AdminBlogOut]:
    paging = parse_page(page, page_size, default_size=50)
    # `is_active`는 3상태다 — true=활성만, false=비활성만, 생략·인식 불가 값=전체.
    # 비활성만 보기가 이 화면의 핵심이다: 자동 비활성화된 피드를 찾아
    # 다시 켜는 것이 목적이다.
    active = lenient_bool(is_active)
    rows, total = await ctx.blog_service.list(paging, active=active)
    return Paged.of_page([AdminBlogOut.of(row) for row in rows], total, paging)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AdminBlogOut)
async def create_blog(ctx: Ctx, _: AdminUser, body: BlogIn) -> AdminBlogOut:
    from techletter.content.service import BlogWithCount  # noqa: PLC0415

    blog = await ctx.blog_service.create(
        name=body.name,
        url=body.url,
        rss_url=body.rss_url,
        is_active=body.is_active,
    )
    return AdminBlogOut.of(BlogWithCount(blog=blog, post_count=0))


@router.put("/{blog_id}", response_model=AdminBlogOut)
async def update_blog(ctx: Ctx, _: AdminUser, blog_id: str, body: BlogIn) -> AdminBlogOut:
    blog = await ctx.blog_service.update(blog_id, body.model_dump())
    return await _with_stats(ctx, blog)


@router.delete("/{blog_id}")
async def delete_blog(
    ctx: Ctx, _: AdminUser, blog_id: str, delete_posts: bool = False
) -> dict[str, int]:
    """블로그를 지운다. `delete_posts=true`면 딸린 포스트와 벡터도 지운다."""
    deleted = await ctx.blog_service.delete(blog_id, delete_posts=delete_posts)
    return {"deleted_posts": deleted}


@router.post("/{blog_id}/activate", response_model=AdminBlogOut)
async def activate_blog(ctx: Ctx, _: AdminUser, blog_id: str) -> AdminBlogOut:
    """자동 비활성화된 블로그를 다시 켠다. 실패 카운터도 지운다."""
    blog = await ctx.blog_service.update(blog_id, {"is_active": True})
    return await _with_stats(ctx, blog)


async def _with_stats(ctx: Ctx, blog: Blog) -> AdminBlogOut:
    from techletter.content.service import BlogWithCount  # noqa: PLC0415

    stats = (await ctx.posts.stats_by_blog([blog.id] if blog.id else [])).get(str(blog.id))
    return AdminBlogOut.of(
        BlogWithCount(
            blog=blog,
            post_count=stats.count if stats else 0,
            last_post_at=stats.last_added_at if stats else None,
        )
    )
