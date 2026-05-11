from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.eventbus.topics import TOPIC_POST_EMBEDDING_DELETE_REQUESTED
from common.events.post import EventType
from common.models.blog import Blog, ListBlogsFilter
from content_service.app.services.blogs_service import (
    BlogNotFoundError,
    BlogsService,
    DuplicateBlogError,
    InvalidBlogTypeError,
)


def _blog(
    id_value: str,
    *,
    name: str = "Blog",
    url: str = "https://example.com",
    rss_url: str = "https://example.com/feed.xml",
) -> Blog:
    now = datetime.now(timezone.utc)
    return Blog(
        id=id_value,
        created_at=now,
        updated_at=now,
        name=name,
        url=url,
        rss_url=rss_url,
        blog_type="company",
        is_active=True,
    )


class FakeBlogRepository:
    def __init__(self) -> None:
        self.items: dict[str, Blog] = {}
        self.next_id = 1

    def list(self, flt: ListBlogsFilter) -> tuple[list[Blog], int]:
        return list(self.items.values()), len(self.items)

    def create(self, blog: Blog) -> str:
        id_value = str(self.next_id)
        self.next_id += 1
        blog.id = id_value
        self.items[id_value] = blog
        return id_value

    def update(self, id_value: str, blog: Blog) -> bool:
        if id_value not in self.items:
            return False
        self.items[id_value] = blog
        return True

    def delete_by_id(self, id_value: str) -> bool:
        return self.items.pop(id_value, None) is not None

    def get_by_rss_url(self, rss_url: str) -> Blog | None:
        return next((item for item in self.items.values() if item.rss_url == rss_url), None)

    def get_by_url(self, url: str) -> Blog | None:
        return next((item for item in self.items.values() if item.url == url), None)

    def find_by_id(self, id_value: str) -> Blog | None:
        return self.items.get(id_value)

    def list_active_sources(self) -> list[Blog]:
        return [item for item in self.items.values() if item.is_active]

    def update_fetch_result(self, id_value: str, error: str | None) -> None:
        raise NotImplementedError


class FakePostRepository:
    def __init__(self) -> None:
        self.deleted_blog_ids: list[str] = []
        self.counts_by_blog_id: dict[str, int] = {}
        self.ids_by_blog_id: dict[str, list[str]] = {}

    def delete_by_blog_id(self, blog_id: str) -> int:
        self.deleted_blog_ids.append(blog_id)
        return 3

    def list_ids_by_blog_id(self, blog_id: str) -> list[str]:
        return self.ids_by_blog_id.get(blog_id, [])

    def count_by_blog_ids(self, blog_ids: list[str]) -> dict[str, int]:
        return {
            blog_id: self.counts_by_blog_id.get(blog_id, 0)
            for blog_id in blog_ids
        }


class FakeEventBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    def publish(self, topic: str, event: object) -> None:
        self.published.append((topic, event))


def _service(
    blog_repo: FakeBlogRepository | None = None,
    post_repo: FakePostRepository | None = None,
    event_bus: FakeEventBus | None = None,
) -> BlogsService:
    return BlogsService(
        blog_repo or FakeBlogRepository(),
        post_repo or FakePostRepository(),
        event_bus or FakeEventBus(),
    )


def test_list_blogs_includes_post_count() -> None:
    blog_repo = FakeBlogRepository()
    post_repo = FakePostRepository()
    blog_repo.items["1"] = _blog("1", name="One")
    blog_repo.items["2"] = _blog("2", name="Two")
    post_repo.counts_by_blog_id = {"1": 7}
    service = _service(blog_repo, post_repo)

    blogs, total = service.list_blogs(ListBlogsFilter())

    assert total == 2
    assert {blog.id: blog.post_count for blog in blogs} == {"1": 7, "2": 0}


def test_create_blog_rejects_duplicate_rss_url() -> None:
    blog_repo = FakeBlogRepository()
    blog_repo.items["existing"] = _blog("existing")
    service = _service(blog_repo)

    with pytest.raises(DuplicateBlogError, match="rss_url already exists"):
        service.create_blog(
            name="Other",
            url="https://other.example.com",
            rss_url="https://example.com/feed.xml",
            blog_type="company",
            is_active=True,
        )


def test_create_blog_rejects_duplicate_rss_url_with_trailing_slash_variant() -> None:
    blog_repo = FakeBlogRepository()
    blog_repo.items["existing"] = _blog(
        "existing",
        rss_url="https://example.com/feed.xml/",
    )
    service = _service(blog_repo)

    with pytest.raises(DuplicateBlogError, match="rss_url already exists"):
        service.create_blog(
            name="Other",
            url="https://other.example.com",
            rss_url="https://example.com/feed.xml",
            blog_type="company",
            is_active=True,
        )


def test_create_blog_rejects_invalid_blog_type() -> None:
    service = _service()

    with pytest.raises(InvalidBlogTypeError, match="blog_type must be one of"):
        service.create_blog(
            name="Other",
            url="https://other.example.com",
            rss_url="https://other.example.com/feed.xml",
            blog_type="newsletter",
            is_active=True,
        )


def test_update_blog_allows_own_urls_but_rejects_other_blog_url() -> None:
    blog_repo = FakeBlogRepository()
    blog_repo.items["1"] = _blog("1", url="https://one.example.com", rss_url="https://one.example.com/feed.xml")
    blog_repo.items["2"] = _blog("2", url="https://two.example.com", rss_url="https://two.example.com/feed.xml")
    service = _service(blog_repo)

    updated = service.update_blog(
        "1",
        name="One Updated",
        url="https://one.example.com",
        rss_url="https://one.example.com/feed.xml",
        blog_type="creator",
        is_active=False,
    )

    assert updated.name == "One Updated"
    assert updated.blog_type == "creator"
    assert updated.is_active is False

    with pytest.raises(DuplicateBlogError, match="url already exists"):
        service.update_blog(
            "1",
            name="One",
            url="https://two.example.com",
            rss_url="https://one.example.com/feed.xml",
            blog_type="company",
            is_active=True,
        )


def test_delete_blog_deletes_posts_only_when_requested() -> None:
    blog_repo = FakeBlogRepository()
    post_repo = FakePostRepository()
    event_bus = FakeEventBus()
    blog_repo.items["1"] = _blog("1")
    service = _service(blog_repo, post_repo, event_bus)

    deleted_posts = service.delete_blog("1", delete_posts=False)

    assert deleted_posts == 0
    assert post_repo.deleted_blog_ids == []
    assert event_bus.published == []
    assert blog_repo.find_by_id("1") is None

    blog_repo.items["2"] = _blog("2")
    post_repo.ids_by_blog_id["2"] = ["post-1", "post-2"]
    deleted_posts = service.delete_blog("2", delete_posts=True)

    assert deleted_posts == 3
    assert post_repo.deleted_blog_ids == ["2"]
    assert [topic for topic, _ in event_bus.published] == [
        TOPIC_POST_EMBEDDING_DELETE_REQUESTED.base,
        TOPIC_POST_EMBEDDING_DELETE_REQUESTED.base,
    ]
    assert [event.payload["type"] for _, event in event_bus.published] == [
        EventType.POST_EMBEDDING_DELETE_REQUESTED,
        EventType.POST_EMBEDDING_DELETE_REQUESTED,
    ]
    assert [event.payload["post_id"] for _, event in event_bus.published] == [
        "post-1",
        "post-2",
    ]


def test_delete_blog_raises_when_blog_does_not_exist() -> None:
    service = _service()

    with pytest.raises(BlogNotFoundError):
        service.delete_blog("missing", delete_posts=True)
