"""어드민 블로그."""

from __future__ import annotations

from fastapi import APIRouter, status

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import AdminBlogOut, BlogIn, Paged
from techletter.api.schemas.query import StrQ, parse_page
from techletter.core.pagination import lenient_bool

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
    # 어드민은 기본적으로 비활성 블로그도 봐야 한다 — 자동 비활성화된 피드를
    # 찾아 다시 켜는 것이 이 화면의 목적이다.
    include_inactive = lenient_bool(is_active) is not True
    rows, total = await ctx.blog_service.list(paging, include_inactive=include_inactive)
    return Paged.of_page([AdminBlogOut.of(row) for row in rows], total, paging)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AdminBlogOut)
async def create_blog(ctx: Ctx, _: AdminUser, body: BlogIn) -> AdminBlogOut:
    from techletter.content.service import BlogWithCount  # noqa: PLC0415

    blog = await ctx.blog_service.create(
        name=body.name,
        url=body.url,
        rss_url=body.rss_url,
        blog_type=body.blog_type,
        is_active=body.is_active,
    )
    return AdminBlogOut.of(BlogWithCount(blog=blog, post_count=0))


@router.put("/{blog_id}", response_model=AdminBlogOut)
async def update_blog(ctx: Ctx, _: AdminUser, blog_id: str, body: BlogIn) -> AdminBlogOut:
    from techletter.content.service import BlogWithCount  # noqa: PLC0415

    blog = await ctx.blog_service.update(blog_id, body.model_dump())
    counts = await ctx.posts.count_by_blog([blog.id] if blog.id else [])
    return AdminBlogOut.of(BlogWithCount(blog=blog, post_count=counts.get(str(blog.id), 0)))


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
    from techletter.content.service import BlogWithCount  # noqa: PLC0415

    blog = await ctx.blog_service.update(blog_id, {"is_active": True})
    return AdminBlogOut.of(BlogWithCount(blog=blog, post_count=0))
