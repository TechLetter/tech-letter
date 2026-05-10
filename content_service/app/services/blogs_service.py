from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from fastapi import Depends
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from common.eventbus.kafka import KafkaEventBus, get_kafka_event_bus
from common.mongo.client import get_database
from common.models.blog import Blog, BlogType, ListBlogsFilter
from ..repositories.blog_repository import BlogRepository
from ..repositories.interfaces import BlogRepositoryInterface
from ..repositories.interfaces import PostRepositoryInterface
from ..repositories.post_repository import PostRepository
from .post_embedding_events import publish_post_embedding_delete_requested


class BlogNotFoundError(ValueError):
    pass


class DuplicateBlogError(ValueError):
    pass


class InvalidBlogTypeError(ValueError):
    pass


def _normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def _url_lookup_candidates(value: str) -> tuple[str, str]:
    normalized = _normalize_url(value)
    return normalized, f"{normalized}/"


def _normalize_blog_type(value: str) -> BlogType:
    blog_type = value.strip() or "company"
    if blog_type not in ("company", "creator"):
        raise InvalidBlogTypeError("blog_type must be one of: company, creator")
    return cast(BlogType, blog_type)


class BlogsService:
    """블로그 목록 조회 비즈니스 로직.

    - Repository(BlogRepository)에만 의존하고, Mongo 세부 구현은 알지 않는다.
    """

    def __init__(
        self,
        blog_repo: BlogRepositoryInterface,
        post_repo: PostRepositoryInterface,
        event_bus: KafkaEventBus,
    ) -> None:
        self._blog_repo = blog_repo
        self._post_repo = post_repo
        self._event_bus = event_bus

    def list_blogs(self, filter_: ListBlogsFilter) -> tuple[list[Blog], int]:
        blogs, total = self._blog_repo.list(filter_)
        blog_ids = [blog.id for blog in blogs if blog.id is not None]
        post_counts = self._post_repo.count_by_blog_ids(blog_ids)
        blogs_with_counts = [
            blog.model_copy(update={"post_count": post_counts.get(blog.id or "", 0)})
            for blog in blogs
        ]
        return blogs_with_counts, total

    def create_blog(
        self,
        *,
        name: str,
        url: str,
        rss_url: str,
        blog_type: str,
        is_active: bool,
    ) -> Blog:
        normalized_url = _normalize_url(url)
        normalized_rss_url = _normalize_url(rss_url)
        self._ensure_unique(
            url=normalized_url,
            rss_url=normalized_rss_url,
            exclude_blog_id=None,
        )

        now = datetime.now(timezone.utc)
        blog = Blog(
            id=None,
            created_at=now,
            updated_at=now,
            name=name.strip(),
            url=normalized_url,
            rss_url=normalized_rss_url,
            blog_type=_normalize_blog_type(blog_type),
            is_active=is_active,
        )
        try:
            blog.id = self._blog_repo.create(blog)
        except DuplicateKeyError as exc:
            raise DuplicateBlogError("rss_url already exists") from exc
        return blog

    def update_blog(
        self,
        blog_id: str,
        *,
        name: str,
        url: str,
        rss_url: str,
        blog_type: str,
        is_active: bool,
    ) -> Blog:
        existing = self._blog_repo.find_by_id(blog_id)
        if existing is None:
            raise BlogNotFoundError(f"blog not found: {blog_id}")

        normalized_url = _normalize_url(url)
        normalized_rss_url = _normalize_url(rss_url)
        self._ensure_unique(
            url=normalized_url,
            rss_url=normalized_rss_url,
            exclude_blog_id=blog_id,
        )

        updated = Blog(
            id=blog_id,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc),
            name=name.strip(),
            url=normalized_url,
            rss_url=normalized_rss_url,
            blog_type=_normalize_blog_type(blog_type),
            is_active=is_active,
            last_fetched_at=existing.last_fetched_at,
            last_fetch_error=existing.last_fetch_error,
        )
        try:
            ok = self._blog_repo.update(blog_id, updated)
        except DuplicateKeyError as exc:
            raise DuplicateBlogError("rss_url already exists") from exc
        if not ok:
            raise BlogNotFoundError(f"blog not found: {blog_id}")
        return updated

    def delete_blog(self, blog_id: str, *, delete_posts: bool) -> int:
        existing = self._blog_repo.find_by_id(blog_id)
        if existing is None:
            raise BlogNotFoundError(f"blog not found: {blog_id}")

        deleted_posts = 0
        deleted_post_ids: list[str] = []
        if delete_posts:
            deleted_post_ids = self._post_repo.list_ids_by_blog_id(blog_id)
            deleted_posts = self._post_repo.delete_by_blog_id(blog_id)

        ok = self._blog_repo.delete_by_id(blog_id)
        if not ok:
            raise BlogNotFoundError(f"blog not found: {blog_id}")

        if delete_posts:
            for post_id in deleted_post_ids:
                publish_post_embedding_delete_requested(
                    self._event_bus,
                    post_id=post_id,
                )
        return deleted_posts

    def _ensure_unique(
        self,
        *,
        url: str,
        rss_url: str,
        exclude_blog_id: str | None,
    ) -> None:
        existing_by_rss = next(
            (
                item
                for candidate in _url_lookup_candidates(rss_url)
                if (item := self._blog_repo.get_by_rss_url(candidate)) is not None
            ),
            None,
        )
        if existing_by_rss and existing_by_rss.id != exclude_blog_id:
            raise DuplicateBlogError("rss_url already exists")

        existing_by_url = next(
            (
                item
                for candidate in _url_lookup_candidates(url)
                if (item := self._blog_repo.get_by_url(candidate)) is not None
            ),
            None,
        )
        if existing_by_url and existing_by_url.id != exclude_blog_id:
            raise DuplicateBlogError("url already exists")


def get_blog_repository(
    db: Database = Depends(get_database),
) -> BlogRepositoryInterface:
    """FastAPI DI용 BlogRepository 팩토리."""

    return BlogRepository(db)


def get_blogs_service(
    repo: BlogRepository = Depends(get_blog_repository),
    db: Database = Depends(get_database),
    event_bus: KafkaEventBus = Depends(get_kafka_event_bus),
) -> BlogsService:
    """FastAPI DI용 BlogsService 팩토리."""

    return BlogsService(repo, PostRepository(db), event_bus)
