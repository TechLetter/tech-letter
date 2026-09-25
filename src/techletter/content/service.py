"""content 도메인 서비스.

저장소 위에서 조회를 조립하고, 변경 후에 잡을 건다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.content.jobs import (
    PostRefPayload,
    enqueue_content_fetch,
    enqueue_embedding_delete,
    enqueue_embedding_requested,
    enqueue_summary_requested,
)
from techletter.content.links import normalize_link
from techletter.content.models import AISummary, Blog, Post, StatusFlags
from techletter.core.errors import (
    ResourceConflictError,
    ResourceNotFoundError,
)
from techletter.core.ids import to_object_id
from techletter.core.jobs.models import PRIORITY_NORMAL
from techletter.core.jobs.types import JobType
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.models import ListPostsFilter
    from techletter.content.repositories import BlogRepository, PostRepository
    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue
    from techletter.core.pagination import Page

__all__ = ["BlogService", "BlogWithCount", "PostService"]

logger = get_logger(__name__)


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


@dataclass(slots=True)
class BlogWithCount:
    blog: Blog
    post_count: int


async def request_summary(
    queue: JobQueue, posts: PostRepository, post: Post, *, priority: int = PRIORITY_NORMAL
) -> tuple[JobType, Job | None]:
    """본문이 이미 있으면 요약만, 없으면 가져오기부터 건다.

    재요약(모델·주제 목록이 바뀌었을 때)에 원문을 다시 받지 않는다. 막힌 원문을
    재시도하며 LLM을 부르는 일도 없다.
    """
    ref = PostRefPayload.of(post)
    if await posts.get_plain_text(ref.post_id):
        return JobType.SUMMARY_REQUESTED, await enqueue_summary_requested(
            queue, ref, priority=priority
        )
    return JobType.CONTENT_FETCH_REQUESTED, await enqueue_content_fetch(
        queue, ref, priority=priority
    )


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
        raw_link = link.strip()
        link_key = normalize_link(raw_link)
        known = await self._posts.existing_link_keys([raw_link], [link_key])
        if raw_link in known or link_key in known:
            raise ResourceConflictError("post with this link already exists", field="link")

        now = utcnow()
        saved = await self._posts.insert(
            Post(
                blog_id=blog.id,
                blog_name=blog.name,
                title=title.strip(),
                link=raw_link,
                link_key=link_key,
                published_at=now,
                status=StatusFlags(),
                aisummary=AISummary(),
            )
        )
        if saved is None:
            raise ResourceConflictError("post with this link already exists", field="link")
        await enqueue_content_fetch(self._queue, PostRefPayload.of(saved))
        return saved

    async def delete(self, post_id: str) -> None:
        if not await self._posts.delete(post_id):
            raise ResourceNotFoundError(f"post not found: {post_id}")
        # 벡터는 별도 저장소(Qdrant)에 있어 문서와 같이 지워지지 않는다.
        await enqueue_embedding_delete(self._queue, [post_id], key=f"post:{post_id}")

    async def retry_summary(self, post_id: str) -> JobType:
        """어드민의 "다시 요약". 어떤 잡을 걸었는지 돌려준다(상태 추적용)."""
        post = await self.get(post_id)
        job_type, _ = await request_summary(self._queue, self._posts, post)
        return job_type

    async def retry_embedding(self, post_id: str) -> None:
        await self.get(post_id)
        await enqueue_embedding_requested(self._queue, post_id)


class BlogService:
    def __init__(self, blogs: BlogRepository, posts: PostRepository, queue: JobQueue) -> None:
        self._blogs = blogs
        self._posts = posts
        self._queue = queue

    async def list(
        self, page: Page, *, active: bool | None = True
    ) -> tuple[list[BlogWithCount], int]:
        blogs, total = await self._blogs.list_blogs(page, active=active)
        counts = await self._posts.count_by_blog([blog.id for blog in blogs if blog.id is not None])
        return [
            BlogWithCount(blog=blog, post_count=counts.get(str(blog.id), 0)) for blog in blogs
        ], total

    async def get(self, blog_id: str) -> Blog:
        blog = await self._blogs.get(blog_id)
        if blog is None:
            raise ResourceNotFoundError(f"blog not found: {blog_id}")
        return blog

    async def create(
        self,
        *,
        name: str,
        url: str,
        rss_url: str,
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
                is_active=is_active,
            )
        )

    async def update(self, blog_id: str, changes: dict[str, object]) -> Blog:
        """부분 갱신 — 전달된 필드만 바뀐다."""
        existing = await self.get(blog_id)
        fields: dict[str, object] = {}
        for key in ("name", "url", "rss_url", "is_active"):
            if key not in changes:
                continue
            value = changes[key]
            if key in ("url", "rss_url"):
                fields[key] = normalize_url(str(value))
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
