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
    from techletter.content.models import Blog, Post
    from techletter.content.service import BlogWithCount
    from techletter.content.trends import RisingTags, TrendSeries

__all__ = [
    "AdminBlogOut",
    "AdminPostOut",
    "AiSummaryOut",
    "BlogFilterOut",
    "BlogOut",
    "EmbeddingOut",
    "FilterOut",
    "PostOut",
    "PostStatusOut",
    "RisingTagOut",
    "RisingTagsOut",
    "SeriesPointOut",
    "SourceOut",
    "TagSeriesOut",
    "TrendSeriesOut",
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


class BlogOut(BaseModel):
    """공개 블로그."""

    id: str
    name: str
    url: str

    @classmethod
    def of(cls, blog: Blog) -> BlogOut:
        return cls(id=str(blog.id), name=blog.name, url=blog.url)


class AdminBlogOut(BaseModel):
    id: str
    name: str
    url: str
    rss_url: str
    blog_type: str
    is_active: bool
    tls_insecure: bool
    post_count: int
    consecutive_failures: int
    last_fetched_at: str | None
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
            blog_type=blog.blog_type,
            is_active=blog.is_active,
            tls_insecure=blog.tls_insecure,
            post_count=row.post_count,
            consecutive_failures=blog.consecutive_failures,
            last_fetched_at=to_iso_z(blog.last_fetched_at),
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


class BlogFilterOut(BaseModel):
    id: str
    name: str
    count: int

    @classmethod
    def of(cls, item: BlogFilterItem) -> BlogFilterOut:
        return cls(id=item.blog_id, name=item.name, count=item.count)


class RisingTagOut(BaseModel):
    tag: str
    current_count: int
    previous_count: int
    delta: int
    growth_rate: float | None


class RisingPeriodOut(BaseModel):
    from_at: str | None
    to: str | None
    previous_from: str | None
    previous_to: str | None


class RisingTagsOut(BaseModel):
    period: RisingPeriodOut
    items: list[RisingTagOut]
    total: int

    @classmethod
    def of(cls, result: RisingTags) -> RisingTagsOut:
        return cls(
            period=RisingPeriodOut(
                from_at=to_iso_z(result.from_at),
                to=to_iso_z(result.to),
                previous_from=to_iso_z(result.previous_from),
                previous_to=to_iso_z(result.previous_to),
            ),
            items=[
                RisingTagOut(
                    tag=item.tag,
                    current_count=item.current_count,
                    previous_count=item.previous_count,
                    delta=item.delta,
                    growth_rate=item.growth_rate,
                )
                for item in result.items
            ],
            total=len(result.items),
        )


class SeriesPointOut(BaseModel):
    bucket: str | None
    post_count: int
    blog_count: int


class TagSeriesOut(BaseModel):
    tag: str
    points: list[SeriesPointOut]


class SeriesPeriodOut(BaseModel):
    from_at: str | None
    to: str | None
    interval: str


class TrendSeriesOut(BaseModel):
    period: SeriesPeriodOut
    items: list[TagSeriesOut]
    total: int

    @classmethod
    def of(cls, result: TrendSeries) -> TrendSeriesOut:
        return cls(
            period=SeriesPeriodOut(
                from_at=to_iso_z(result.from_at),
                to=to_iso_z(result.to),
                interval=result.interval,
            ),
            items=[
                TagSeriesOut(
                    tag=series.tag,
                    points=[
                        SeriesPointOut(
                            bucket=to_iso_z(point.bucket),
                            post_count=point.post_count,
                            blog_count=point.blog_count,
                        )
                        for point in series.points
                    ],
                )
                for series in result.series
            ],
            total=len(result.series),
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
