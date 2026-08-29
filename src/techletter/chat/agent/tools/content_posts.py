"""포스트 조회 도구.

현행은 챗봇이 content-service에 HTTP로 물었고, 본문은 **포스트마다 한 번씩**
더 요청했다(N+1). 같은 프로세스가 됐으니 저장소를 직접 부르고 본문은 한 번에
가져온다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.chat.agent.state import PostRecord, Source, ToolResult
from techletter.content.models import ListPostsFilter
from techletter.core.pagination import Page
from techletter.core.time import to_iso_z

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.agent.state import PostConstraints
    from techletter.content.models import Post
    from techletter.content.repositories import PostRepository

__all__ = ["PostLookupTool", "describe_constraints"]


def describe_constraints(constraints: PostConstraints) -> str:
    """사용자에게 보여줄 조건 설명. "무엇으로 찾았는지"를 답변에 남긴다."""
    parts: list[str] = []
    if constraints.published_from:
        parts.append(f"{to_iso_z(constraints.published_from)} 이후")
    if constraints.published_to:
        parts.append(f"{to_iso_z(constraints.published_to)} 이전")
    if constraints.blog_name:
        parts.append(f"{constraints.blog_name} 블로그")
    if constraints.categories:
        parts.append("카테고리 " + ", ".join(constraints.categories))
    if constraints.tags:
        parts.append("태그 " + ", ".join(constraints.tags))
    return ", ".join(parts) if parts else "최신순"


def _record(post: Post) -> PostRecord:
    summary = post.aisummary.summary if post.aisummary else ""
    return PostRecord(
        id=str(post.id),
        title=post.title,
        link=post.link,
        blog_name=post.blog_name,
        published_at=to_iso_z(post.published_at) or "",
        summary=summary or "",
        categories=post.aisummary.categories if post.aisummary else [],
        tags=post.aisummary.tags if post.aisummary else [],
    )


class PostLookupTool:
    def __init__(self, posts: PostRepository) -> None:
        self._posts = posts

    async def list_posts(self, constraints: PostConstraints) -> ToolResult:
        found, total = await self._posts.list_posts(
            ListPostsFilter(
                categories=constraints.categories,
                tags=constraints.tags,
                published_from=constraints.published_from,
                published_to=constraints.published_to,
                # 챗봇은 요약이 끝난 글만 다룬다. 요약이 없으면 인용할 내용이 없다.
                summarized=True,
                search=constraints.blog_name,
            ),
            Page(page=1, page_size=constraints.limit),
        )
        described = describe_constraints(constraints)
        if not found:
            return ToolResult(
                status="no_result",
                total=total,
                message=f"{described} 조건에 맞는 포스트를 찾지 못했습니다.",
            )
        records = [_record(post) for post in found]
        return ToolResult(
            status="ok",
            posts=records,
            sources=[
                Source(
                    post_id=record.id,
                    title=record.title,
                    blog_name=record.blog_name,
                    link=record.link,
                )
                for record in records
            ],
            total=total,
            message=f"{described} 조건으로 포스트를 조회했습니다.",
        )

    async def hydrate(self, records: list[PostRecord]) -> list[PostRecord]:
        """본문을 한 번의 질의로 채운다. 현행은 포스트마다 HTTP를 쳤다."""
        bodies = await self._posts.get_plain_texts([record.id for record in records])
        for record in records:
            record.plain_text = bodies.get(record.id)
        return records
