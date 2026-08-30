"""RSS 수집 한 사이클 — 실제 Mongo + 가짜 HTTP."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from techletter.content.models import Blog, ListPostsFilter
from techletter.content.repositories import BlogRepository, PostRepository
from techletter.content.rss.aggregator import Aggregator
from techletter.content.rss.feeder import RssFeeder
from techletter.core.http import HttpClients
from techletter.core.jobs.types import JobType
from techletter.core.pagination import Page

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "fixtures" / "rss"
FEED = (FIXTURES / "rss2.xml").read_text(encoding="utf-8")


def feeder_for(routes: dict[str, httpx.Response]) -> RssFeeder:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    clients = HttpClients()
    clients._secure = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    clients._insecure = clients._secure
    return RssFeeder(clients)


@pytest.fixture
async def blog(mongo_db) -> Blog:
    return await BlogRepository(mongo_db).insert(
        Blog(name="Alpha", url="https://alpha.test", rss_url="https://alpha.test/rss")
    )


async def test_new_items_are_stored_and_queued(mongo_db, queue, blog) -> None:
    aggregator = Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(200, text=FEED)}),
        queue,
    )

    result = await aggregator.run()

    assert result.inserted == 2
    assert result.blogs[0].fetched == 2
    _, total = await PostRepository(mongo_db).list_posts(ListPostsFilter(), Page(1, 10))
    assert total == 2
    assert await mongo_db["jobs"].count_documents({"type": JobType.SUMMARY_REQUESTED.value}) == 2


async def test_a_second_cycle_inserts_nothing(mongo_db, queue, blog) -> None:
    aggregator = Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(200, text=FEED)}),
        queue,
    )
    await aggregator.run()

    second = await aggregator.run()

    assert second.inserted == 0
    assert await mongo_db["jobs"].count_documents({}) == 2


async def test_queued_job_carries_what_the_summary_worker_needs(mongo_db, queue, blog) -> None:
    await Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(200, text=FEED)}),
        queue,
    ).run()

    job = await mongo_db["jobs"].find_one({"type": JobType.SUMMARY_REQUESTED.value})

    assert job is not None
    assert set(job["payload"]) == {"post_id", "title", "link", "blog_name"}
    assert job["payload"]["blog_name"] == "Alpha"
    assert job["key"] == job["payload"]["post_id"]


async def test_success_records_the_fetch_time(mongo_db, queue, blog) -> None:
    await Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(200, text=FEED)}),
        queue,
    ).run()

    found = await BlogRepository(mongo_db).get(str(blog.id))

    assert found is not None
    assert found.last_fetched_at is not None
    assert found.last_fetch_error is None


async def test_one_broken_feed_does_not_stop_the_others(mongo_db, queue, blog) -> None:
    blogs = BlogRepository(mongo_db)
    await blogs.insert(
        Blog(name="Broken", url="https://broken.test", rss_url="https://broken.test/rss")
    )

    result = await Aggregator(
        blogs,
        PostRepository(mongo_db),
        feeder_for(
            {
                "https://alpha.test/rss": httpx.Response(200, text=FEED),
                "https://broken.test/rss": httpx.Response(500),
            }
        ),
        queue,
    ).run()

    assert result.inserted == 2
    assert result.failed == 1


async def test_failure_message_does_not_leak_the_response_body(mongo_db, queue, blog) -> None:
    """어드민 화면에 404 HTML이 그대로 뜨면 안 된다."""
    await Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(404, text="<html>Not Found</html>")}),
        queue,
    ).run()

    found = await BlogRepository(mongo_db).get(str(blog.id))

    assert found is not None
    assert found.last_fetch_error is not None
    assert "<html>" not in found.last_fetch_error
    assert "404" in found.last_fetch_error


async def test_a_permanently_dead_feed_is_disabled_after_the_threshold(
    mongo_db, queue, blog
) -> None:
    aggregator = Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(404)}),
        queue,
        failure_threshold=3,
    )

    for _ in range(2):
        assert (await aggregator.run()).blogs[0].deactivated is False
    third = await aggregator.run()

    assert third.blogs[0].deactivated is True
    found = await BlogRepository(mongo_db).get(str(blog.id))
    assert found is not None and found.is_active is False


async def test_temporary_failures_never_disable_a_blog(mongo_db, queue, blog) -> None:
    """5xx 는 블로그 쪽 사고다. 자동으로 끄면 사람이 다시 켜야 한다."""
    aggregator = Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(503)}),
        queue,
        failure_threshold=2,
    )

    for _ in range(4):
        await aggregator.run()

    found = await BlogRepository(mongo_db).get(str(blog.id))
    assert found is not None and found.is_active is True


async def test_inactive_blogs_are_skipped(mongo_db, queue) -> None:
    blogs = BlogRepository(mongo_db)
    await blogs.insert(
        Blog(
            name="Off",
            url="https://off.test",
            rss_url="https://off.test/rss",
            is_active=False,
        )
    )

    result = await Aggregator(
        blogs,
        PostRepository(mongo_db),
        feeder_for({"https://off.test/rss": httpx.Response(200, text=FEED)}),
        queue,
    ).run()

    assert result.blogs == []


async def test_batch_size_limits_items_per_blog(mongo_db, queue, blog) -> None:
    result = await Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(200, text=FEED)}),
        queue,
        batch_size=1,
    ).run()

    assert result.inserted == 1


async def test_items_without_a_publish_date_still_get_one(mongo_db, queue, blog) -> None:
    atom = (FIXTURES / "atom.xml").read_text(encoding="utf-8")

    await Aggregator(
        BlogRepository(mongo_db),
        PostRepository(mongo_db),
        feeder_for({"https://alpha.test/rss": httpx.Response(200, text=atom)}),
        queue,
    ).run()

    found, _ = await PostRepository(mongo_db).list_posts(ListPostsFilter(), Page(1, 10))
    assert all(post.published_at is not None for post in found)
