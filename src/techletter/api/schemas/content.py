"""포스트·블로그·필터·트렌드 DTO.

DB 필드명과 다른 부분이 여기서 바뀐다: `aisummary` → `ai_summary`,
`status.ai_summarized` → `status.summarized`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from techletter.core.time import to_iso_z

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.agent.state import Source
    from techletter.content.filters import BlogFilterItem, FilterItem
    from techletter.content.models import Post
    from techletter.content.service import BlogWithCount
    from techletter.content.trends import WeeklyTrends
    from techletter.summary.topics import TopicGroup

__all__ = [
    "AdminBlogOut",
    "AdminPostOut",
    "AiSummaryOut",
    "BlogFilterOut",
    "EmbeddingOut",
    "FilterOut",
    "PostOut",
    "PostStatusOut",
    "SourceOut",
    "TopicGroupOut",
    "TopicTrendOut",
    "WeeklyTrendsOut",
]


class PostOut(BaseModel):
    """공개 포스트."""

    id: str
    blog_id: str | None
    blog_name: str
    title: str
    link: str
    published_at: str | None
    thumbnail_url: str | None
    view_count: int
    summary: str | None
    categories: list[str]
    tags: list[str]
    is_bookmarked: bool

    @classmethod
    def of(cls, post: Post, *, bookmarked: bool = False) -> PostOut:
        summary = post.aisummary
        return cls(
            id=str(post.id),
            blog_id=str(post.blog_id) if post.blog_id else None,
            blog_name=post.blog_name,
            title=post.title,
            link=post.link,
            published_at=to_iso_z(post.published_at),
            # 빈 문자열을 그대로 내보내면 프론트가 깨진 이미지를 그린다.
            thumbnail_url=post.thumbnail_url or None,
            view_count=post.view_count,
            summary=(summary.summary or None) if summary else None,
            # 요약 전이면 빈 배열. null이 아니다.
            categories=summary.categories if summary else [],
            tags=summary.tags if summary else [],
            # 익명 요청이면 false. 키가 없는 3상태를 없앤다.
            is_bookmarked=bookmarked,
        )


class AdminBlogOut(BaseModel):
    id: str
    name: str
    url: str
    rss_url: str
    is_active: bool
    post_count: int
    consecutive_failures: int
    last_fetched_at: str | None
    """RSS를 마지막으로 읽은 때. 새 글이 없어도 바뀐다."""
    last_post_at: str | None
    """마지막으로 새 글이 들어온 때."""
    last_fetch_error: str | None
    created_at: str | None
    updated_at: str | None

    @classmethod
    def of(cls, row: BlogWithCount) -> AdminBlogOut:
        blog = row.blog
        return cls(
            id=str(blog.id),
            name=blog.name,
            url=blog.url,
            rss_url=blog.rss_url,
            is_active=blog.is_active,
            post_count=row.post_count,
            consecutive_failures=blog.consecutive_failures,
            last_fetched_at=to_iso_z(blog.last_fetched_at),
            last_post_at=to_iso_z(row.last_post_at),
            last_fetch_error=blog.last_fetch_error,
            created_at=to_iso_z(blog.created_at),
            updated_at=to_iso_z(blog.updated_at),
        )


class PostStatusOut(BaseModel):
    summarized: bool
    embedded: bool
    failed_reason: str | None = None


class AiSummaryOut(BaseModel):
    summary: str | None
    categories: list[str]
    tags: list[str]
    model_name: str | None
    generated_at: str | None


class EmbeddingOut(BaseModel):
    model_name: str
    collection_name: str
    vector_dimension: int
    chunk_count: int
    embedded_at: str | None


class AdminPostOut(BaseModel):
    """어드민 포스트."""

    id: str
    title: str
    link: str
    blog_id: str | None
    blog_name: str
    published_at: str | None
    thumbnail_url: str | None
    view_count: int
    status: PostStatusOut
    ai_summary: AiSummaryOut | None
    embedding: EmbeddingOut | None
    created_at: str | None
    updated_at: str | None

    @classmethod
    def of(cls, post: Post) -> AdminPostOut:
        summary = post.aisummary
        embedding = post.embedding
        return cls(
            id=str(post.id),
            title=post.title,
            link=post.link,
            blog_id=str(post.blog_id) if post.blog_id else None,
            blog_name=post.blog_name,
            published_at=to_iso_z(post.published_at),
            thumbnail_url=post.thumbnail_url or None,
            view_count=post.view_count,
            status=PostStatusOut(
                summarized=post.status.ai_summarized,
                embedded=post.status.embedded,
                failed_reason=post.status.failed_reason,
            ),
            ai_summary=(
                AiSummaryOut(
                    summary=summary.summary or None,
                    categories=summary.categories,
                    tags=summary.tags,
                    model_name=summary.model_name or None,
                    generated_at=to_iso_z(summary.generated_at),
                )
                if summary
                else None
            ),
            embedding=(
                EmbeddingOut(
                    model_name=embedding.model_name,
                    collection_name=embedding.collection_name,
                    vector_dimension=embedding.vector_dimension,
                    chunk_count=embedding.chunk_count,
                    embedded_at=to_iso_z(embedding.embedded_at),
                )
                if embedding
                else None
            ),
            created_at=to_iso_z(post.created_at),
            updated_at=to_iso_z(post.updated_at),
        )


class FilterOut(BaseModel):
    name: str
    count: int

    @classmethod
    def of(cls, item: FilterItem) -> FilterOut:
        return cls(name=item.name, count=item.count)


class TopicGroupOut(BaseModel):
    id: str
    name: str
    topics: list[str]
    """자식 주제의 한국어 이름. 포스트의 `categories`와 같은 값이다."""

    @classmethod
    def of(cls, group: TopicGroup) -> TopicGroupOut:
        from techletter.summary.topics import TOPICS  # noqa: PLC0415

        names = {topic.slug: topic.name for topic in TOPICS}
        return cls(id=group.slug, name=group.name, topics=[names[s] for s in group.topics])


class BlogFilterOut(BaseModel):
    id: str
    name: str
    count: int

    @classmethod
    def of(cls, item: BlogFilterItem) -> BlogFilterOut:
        return cls(id=item.blog_id, name=item.name, count=item.count)


class TopicTrendOut(BaseModel):
    topic: str
    blog_count: int
    post_count: int
    previous_blog_count: int
    previous_post_count: int
    posts: list[PostOut]


class WeeklyPeriodOut(BaseModel):
    from_at: str | None
    to: str | None
    previous_from: str | None
    previous_to: str | None


class WeeklyTrendsOut(BaseModel):
    period: WeeklyPeriodOut
    post_count: int
    blog_count: int
    items: list[TopicTrendOut]

    @classmethod
    def of(cls, result: WeeklyTrends, bookmarked: set[str]) -> WeeklyTrendsOut:
        return cls(
            period=WeeklyPeriodOut(
                from_at=to_iso_z(result.from_at),
                to=to_iso_z(result.to),
                previous_from=to_iso_z(result.previous_from),
                previous_to=to_iso_z(result.previous_to),
            ),
            post_count=result.post_count,
            blog_count=result.blog_count,
            items=[
                TopicTrendOut(
                    topic=item.topic,
                    blog_count=item.blog_count,
                    post_count=item.post_count,
                    previous_blog_count=item.previous_blog_count,
                    previous_post_count=item.previous_post_count,
                    posts=[
                        PostOut.of(post, bookmarked=str(post.id) in bookmarked)
                        for post in item.posts
                    ],
                )
                for item in result.items
            ],
        )


class SourceOut(BaseModel):
    post_id: str
    title: str
    blog_name: str
    link: str
    score: float | None = None

    @classmethod
    def of(cls, source: Source) -> SourceOut:
        return cls(
            post_id=source.post_id,
            title=source.title,
            blog_name=source.blog_name,
            link=source.link,
            score=source.score,
        )
