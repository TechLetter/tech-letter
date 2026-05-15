from __future__ import annotations

from ...domain.chat.schemas import PostConstraints, PostRecord, Source, ToolResult
from ...services.content_post_client import ContentPostClient, PostListParams


class ContentPostQueryAdapter:
    def __init__(self, client: ContentPostClient) -> None:
        self._client = client

    def list_posts(self, constraints: PostConstraints) -> ToolResult:
        result = self._client.list_posts(
            PostListParams(
                page=1,
                page_size=constraints.limit,
                categories=constraints.categories,
                tags=constraints.tags,
                blog_name=constraints.blog_name,
                published_from=constraints.published_from,
                published_to=constraints.published_to,
            )
        )
        posts = [
            PostRecord(
                id=item.id,
                title=item.title,
                link=item.link,
                blog_name=item.blog_name,
                published_at=item.published_at,
                summary=item.summary,
                categories=item.categories,
                tags=item.tags,
            )
            for item in result.items
        ]
        if not posts:
            return ToolResult(
                status="no_result",
                posts=[],
                sources=[],
                total=result.total,
                message=_describe_constraints(constraints)
                + " 조건에 맞는 포스트를 찾지 못했습니다.",
            )
        return ToolResult(
            status="ok",
            posts=posts,
            sources=[
                Source(
                    title=post.title,
                    blog_name=post.blog_name,
                    link=post.link,
                    score=1.0,
                )
                for post in posts
            ],
            total=result.total,
            message=_describe_constraints(constraints) + " 조건으로 포스트를 조회했습니다.",
        )

    def hydrate_content(self, posts: list[PostRecord]) -> list[PostRecord]:
        hydrated: list[PostRecord] = []
        for post in posts:
            plain_text = self._client.get_plain_text(post.id)
            post.plain_text = plain_text
            hydrated.append(post)
        return hydrated


def _describe_constraints(constraints: PostConstraints) -> str:
    parts: list[str] = []
    if constraints.published_from:
        parts.append(f"{constraints.published_from.isoformat()} 이후")
    if constraints.published_to:
        parts.append(f"{constraints.published_to.isoformat()} 이전")
    if constraints.blog_name:
        parts.append(f"{constraints.blog_name} 블로그")
    if constraints.categories:
        parts.append("카테고리 " + ", ".join(constraints.categories))
    if constraints.tags:
        parts.append("태그 " + ", ".join(constraints.tags))
    return ", ".join(parts) if parts else "최신순"
