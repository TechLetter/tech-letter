"""content 도메인 서비스.

저장소 위에서 조회를 조립하고, 변경 후에 잡을 건다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.content.jobs import (
    enqueue_embedding_delete,
    enqueue_embedding_requested,
    enqueue_summary_requested,
)
from techletter.content.models import AISummary, Blog, Post, StatusFlags
from techletter.core.errors import (
    InvalidRequestError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from techletter.core.ids import to_object_id
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.models import ListPostsFilter
    from techletter.content.repositories import BlogRepository, PostRepository
    from techletter.core.jobs.queue import JobQueue
    from techletter.core.pagination import Page

__all__ = ["BlogService", "BlogWithCount", "PostService"]

logger = get_logger(__name__)

BLOG_TYPES = frozenset({"company", "creator"})


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


@dataclass(slots=True)
class BlogWithCount:
    blog: Blog
    post_count: int


class PostService:
    def __init__(self, posts: PostRepository, blogs: BlogRepository, queue: JobQueue) -> None:
        self._posts = posts
        self._blogs = blogs
        self._queue = queue

    async def list(self, flt: ListPostsFilter, page: Page) -> tuple[list[Post], int]:
        return await self._posts.list_posts(flt, page)

    async def get(self, post_id: str) -> Post:
        post = await self._posts.get(post_id)
        if post is None:
            raise ResourceNotFoundError(f"post not found: {post_id}")
        return post

    async def get_many(self, post_ids: list[str]) -> list[Post]:
        """요청한 순서를 유지한다. 없는 id는 조용히 빠진다(북마크 화면용)."""
        found = await self._posts.get_many(post_ids)
        return [found[pid] for pid in post_ids if pid in found]

    async def view(self, post_id: str) -> None:
        if not await self._posts.increment_view(post_id):
            raise ResourceNotFoundError(f"post not found: {post_id}")

    async def create(self, *, title: str, link: str, blog_id: str) -> Post:
        """어드민의 수동 등록. 저장 후 요약 잡을 건다."""
        blog = await self._blogs.get(blog_id)
        if blog is None:
            raise ResourceNotFoundError(f"blog not found: {blog_id}")
        if await self._posts.exists_by_link(link):
            raise ResourceConflictError("post with this link already exists", field="link")

        now = utcnow()
        saved = await self._posts.insert(
            Post(
                blog_id=blog.id,
                blog_name=blog.name,
                title=title.strip(),
                link=link.strip(),
                published_at=now,
                status=StatusFlags(),
                aisummary=AISummary(),
            )
        )
        if saved is None:
            raise ResourceConflictError("post with this link already exists", field="link")
        await enqueue_summary_requested(self._queue, saved)
        return saved

    async def delete(self, post_id: str) -> None:
        if not await self._posts.delete(post_id):
            raise ResourceNotFoundError(f"post not found: {post_id}")
        # 벡터는 별도 저장소(Qdrant)에 있어 문서와 같이 지워지지 않는다.
        await enqueue_embedding_delete(self._queue, [post_id], key=f"post:{post_id}")

    async def retry_summary(self, post_id: str) -> None:
        post = await self.get(post_id)
        await enqueue_summary_requested(self._queue, post)

    async def retry_embedding(self, post_id: str) -> None:
        await self.get(post_id)
        await enqueue_embedding_requested(self._queue, post_id)


class BlogService:
    def __init__(self, blogs: BlogRepository, posts: PostRepository, queue: JobQueue) -> None:
        self._blogs = blogs
        self._posts = posts
        self._queue = queue

    async def list(
        self, page: Page, *, include_inactive: bool = False
    ) -> tuple[list[BlogWithCount], int]:
        blogs, total = await self._blogs.list_blogs(page, include_inactive=include_inactive)
        counts = await self._posts.count_by_blog([blog.id for blog in blogs if blog.id is not None])
        return [
            BlogWithCount(blog=blog, post_count=counts.get(str(blog.id), 0)) for blog in blogs
        ], total

    async def get(self, blog_id: str) -> Blog:
        blog = await self._blogs.get(blog_id)
        if blog is None:
            raise ResourceNotFoundError(f"blog not found: {blog_id}")
        return blog

    @staticmethod
    def _check_type(blog_type: str) -> str:
        value = blog_type.strip() or "company"
        if value not in BLOG_TYPES:
            raise InvalidRequestError(
                "blog_type must be one of: company, creator",
                details={"field": "blog_type", "allowed": sorted(BLOG_TYPES)},
            )
        return value

    async def create(
        self,
        *,
        name: str,
        url: str,
        rss_url: str,
        blog_type: str = "company",
        is_active: bool = True,
    ) -> Blog:
        url, rss_url = normalize_url(url), normalize_url(rss_url)
        if conflict := await self._blogs.find_conflict(url=url, rss_url=rss_url, exclude_id=None):
            raise ResourceConflictError(f"{conflict} already exists", field=conflict)
        return await self._blogs.insert(
            Blog(
                name=name.strip(),
                url=url,
                rss_url=rss_url,
                blog_type=self._check_type(blog_type),  # type: ignore[arg-type]
                is_active=is_active,
            )
        )

    async def update(self, blog_id: str, changes: dict[str, object]) -> Blog:
        """부분 갱신. 현행은 전체 교체라 `last_fetched_at` 같은 필드가 날아갔다."""
        existing = await self.get(blog_id)
        fields: dict[str, object] = {}
        for key in ("name", "url", "rss_url", "blog_type", "is_active", "tls_insecure"):
            if key not in changes:
                continue
            value = changes[key]
            if key in ("url", "rss_url"):
                fields[key] = normalize_url(str(value))
            elif key == "blog_type":
                fields[key] = self._check_type(str(value))
            elif key == "name":
                fields[key] = str(value).strip()
            else:
                fields[key] = bool(value)

        if "url" in fields or "rss_url" in fields:
            conflict = await self._blogs.find_conflict(
                url=str(fields.get("url", existing.url)),
                rss_url=str(fields.get("rss_url", existing.rss_url)),
                exclude_id=existing.id,
            )
            if conflict:
                raise ResourceConflictError(f"{conflict} already exists", field=conflict)

        # 다시 활성화하면 실패 카운터를 지운다. 안 그러면 임계치를 넘긴 채로
        # 돌아와 첫 실패에 바로 다시 꺼진다.
        if fields.get("is_active") is True and not existing.is_active:
            fields["consecutive_failures"] = 0
            fields["last_fetch_error"] = None

        if not fields:
            return existing
        updated = await self._blogs.update(blog_id, fields)
        if updated is None:
            raise ResourceNotFoundError(f"blog not found: {blog_id}")
        return updated

    async def delete(self, blog_id: str, *, delete_posts: bool = False) -> int:
        blog = await self.get(blog_id)
        oid = to_object_id(blog_id)
        if oid is None:  # get()이 통과했으니 여기 올 수 없다.
            raise ResourceNotFoundError(f"blog not found: {blog_id}")

        deleted = 0
        if delete_posts:
            post_ids = await self._posts.ids_by_blog(oid)
            deleted = await self._posts.delete_by_blog(oid)
            # 포스트 수백 개를 잡 수백 개로 만들지 않고 한 건에 묶는다.
            await enqueue_embedding_delete(self._queue, post_ids, key=f"blog:{blog_id}")

        if not await self._blogs.delete(blog_id):
            raise ResourceNotFoundError(f"blog not found: {blog_id}")
        logger.info(
            "blog deleted",
            extra={"blog": blog.name, "deleted_posts": deleted},
        )
        return deleted
