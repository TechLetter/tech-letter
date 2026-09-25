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

    async def find_by_titles(self, blog_id, titles: list[str]) -> list[Post]:
        return [p for p in self.saved if p.blog_id == blog_id and p.title in titles]

    async def relink(self, post_id: str, link: str, link_key: str) -> bool:
        for post in self.saved:
            if str(post.id) == post_id:
                post.link, post.link_key = link, link_key
                return True
        return False


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


async def _seed(posts: FakePosts, blog: Blog, title: str, link: str) -> Post:
    old = Post(blog_id=blog.id, title=title, link=link, link_key=link)
    return await posts.insert(old)


async def test_a_post_that_moved_domains_is_relinked_not_duplicated() -> None:
    """쏘카는 도메인을 옮기며 .html을 떼고 날짜를 하루 옮겼다. 같은 글이다."""
    posts, queue = FakePosts(), FakeQueue()
    aggregator = Aggregator(None, posts, None, queue)  # type: ignore[arg-type]
    blog = Blog(name="쏘카")
    blog.id = ObjectId()
    old = await _seed(
        posts, blog, "프레임 2편", "https://tech.socarcorp.kr/fe/2026/02/24/frame2-web.html"
    )

    inserted = await aggregator._store(
        blog, [FeedItem("프레임 2편", "https://tech.socar.kr/fe/2026/02/25/frame2-web", None)]
    )

    assert inserted == 0
    assert len(posts.saved) == 1
    assert old.link == "https://tech.socar.kr/fe/2026/02/25/frame2-web"
    assert queue.enqueued == []


async def test_a_repeated_title_with_another_slug_is_a_new_post() -> None:
    """ "월간 소식"처럼 제목이 반복되는 글은 주소 끝부분이 달라 별개다."""
    posts, queue = FakePosts(), FakeQueue()
    aggregator = Aggregator(None, posts, None, queue)  # type: ignore[arg-type]
    blog = Blog(name="Alpha")
    blog.id = ObjectId()
    await _seed(posts, blog, "월간 소식", "https://alpha.test/news-2026-08")

    inserted = await aggregator._store(
        blog, [FeedItem("월간 소식", "https://alpha.test/news-2026-09", None)]
    )

    assert inserted == 1
    assert len(posts.saved) == 2
