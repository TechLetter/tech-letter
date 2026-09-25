"""RSS 수집기의 링크 키 중복 판정."""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId

from techletter.content.models import Blog, Post
from techletter.content.rss.aggregator import Aggregator
from techletter.content.rss.feeder import FeedItem


class FakePosts:
    def __init__(self) -> None:
        self.saved: list[Post] = []

    async def existing_link_keys(self, links: list[str], keys: list[str]) -> set[str]:
        known: set[str] = set()
        for post in self.saved:
            if post.link in links:
                known.add(post.link)
            if post.link_key in keys:
                known.add(post.link_key)
        return known

    async def insert(self, post: Post) -> Post:
        post.id = ObjectId()
        self.saved.append(post)
        return post


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue(self, job_type, key, payload=None, **kwargs):
        self.enqueued.append(key)
        return object()


async def test_variants_of_one_link_are_inserted_once() -> None:
    posts = FakePosts()
    queue = FakeQueue()
    aggregator = Aggregator(None, posts, None, queue)  # type: ignore[arg-type]
    blog = Blog(name="Alpha")
    blog.id = ObjectId()
    published_at = datetime(2026, 1, 1, tzinfo=UTC)
    items = [
        FeedItem("first", "https://example.com/article?utm_source=rss", published_at),
        FeedItem("same article", "https://example.com/article", published_at),
    ]

    inserted = await aggregator._store(blog, items)

    assert inserted == 1
    assert len(posts.saved) == 1
    assert posts.saved[0].link_key == "https://example.com/article"
    assert len(queue.enqueued) == 1


async def test_the_feed_body_is_stored_with_the_post() -> None:
    posts = FakePosts()
    aggregator = Aggregator(None, posts, None, FakeQueue())  # type: ignore[arg-type]
    blog = Blog(name="Alpha")
    blog.id = ObjectId()
    item = FeedItem("a", "https://example.com/a", None, content_html="<p>본문</p>")

    await aggregator._store(blog, [item])

    assert posts.saved[0].feed_html == "<p>본문</p>"
