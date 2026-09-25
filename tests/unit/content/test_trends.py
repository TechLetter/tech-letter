"""주간 기술 흐름 — 순위는 다룬 회사 수, 대표 글은 회사가 겹치지 않게."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bson import ObjectId

from techletter.content.models import Post
from techletter.content.repositories import TopicActivity
from techletter.content.trends import TrendsService, pick_representatives

NOW = datetime(2026, 9, 25, tzinfo=UTC)


class FakePosts:
    def __init__(self, current: list[TopicActivity], previous: list[TopicActivity]) -> None:
        self._by_window = {NOW - timedelta(days=7): current, NOW - timedelta(days=14): previous}
        self.windows: list[tuple[datetime, datetime]] = []

    async def topic_activity(self, published_from, published_to):
        self.windows.append((published_from, published_to))
        return self._by_window[published_from]

    async def activity_totals(self, published_from, published_to):
        return 42, 9

    async def get_many(self, post_ids):
        return {pid: Post(title=pid) for pid in post_ids}


def activity(topic: str, posts: int, blogs: int, recent=()) -> TopicActivity:
    return TopicActivity(topic=topic, post_count=posts, blog_count=blogs, recent=list(recent))


def test_representatives_prefer_distinct_blogs() -> None:
    recent = [("a1", "AWS"), ("a2", "AWS"), ("t1", "토스"), ("a3", "AWS"), ("k1", "카카오")]

    assert pick_representatives(recent) == ["a1", "t1", "k1"]


def test_representatives_fill_up_when_few_blogs_wrote() -> None:
    recent = [("a1", "AWS"), ("a2", "AWS"), ("a3", "AWS"), ("t1", "토스")]

    assert pick_representatives(recent) == ["a1", "t1", "a2"]


async def test_topics_rank_by_blog_count_not_post_count() -> None:
    """한 회사가 글을 몰아 써도 1위가 되지 않는다."""
    posts = FakePosts(
        current=[
            activity("클라우드 아키텍처", posts=16, blogs=1),
            activity("AI 에이전트·MCP", posts=6, blogs=5),
            activity("RAG·검색", posts=7, blogs=5),
        ],
        previous=[activity("AI 에이전트·MCP", posts=2, blogs=2)],
    )

    result = await TrendsService(posts).weekly(limit=8, now=NOW)  # type: ignore[arg-type]

    assert [i.topic for i in result.items] == ["RAG·검색", "AI 에이전트·MCP", "클라우드 아키텍처"]
    agents = result.items[1]
    assert (agents.previous_blog_count, agents.previous_post_count) == (2, 2)
    assert result.items[0].previous_blog_count == 0  # 직전 주에 없던 주제
    assert (result.post_count, result.blog_count) == (42, 9)


async def test_the_windows_are_last_week_and_the_week_before() -> None:
    posts = FakePosts(current=[], previous=[])

    result = await TrendsService(posts).weekly(limit=8, now=NOW)  # type: ignore[arg-type]

    assert posts.windows == [
        (NOW - timedelta(days=7), NOW),
        (NOW - timedelta(days=14), NOW - timedelta(days=7)),
    ]
    assert result.previous_to == result.from_at


async def test_other_is_left_out_and_the_limit_applies() -> None:
    posts = FakePosts(
        current=[activity("기타", 30, 20)] + [activity(f"주제{i}", 1, 10 - i) for i in range(10)],
        previous=[],
    )

    result = await TrendsService(posts).weekly(limit=3, now=NOW)  # type: ignore[arg-type]

    assert [i.topic for i in result.items] == ["주제0", "주제1", "주제2"]


async def test_representative_posts_are_loaded_in_order() -> None:
    oid = str(ObjectId())
    posts = FakePosts(current=[activity("모바일", 1, 1, recent=[(oid, "라인")])], previous=[])

    result = await TrendsService(posts).weekly(limit=8, now=NOW)  # type: ignore[arg-type]

    assert [p.title for p in result.items[0].posts] == [oid]


async def test_a_post_is_shown_under_one_topic_only() -> None:
    """주제가 여러 개인 글은 순위가 높은 카드에만 나온다."""
    shared = [("p1", "Apple ML"), ("p2", "Meta")]
    posts = FakePosts(
        current=[
            activity("멀티모달·비전·음성", 2, 3, recent=[*shared, ("p3", "구글")]),
            activity("온디바이스·엣지 AI", 2, 2, recent=[*shared, ("p4", "라인")]),
        ],
        previous=[],
    )

    result = await TrendsService(posts).weekly(limit=8, now=NOW)  # type: ignore[arg-type]

    assert [p.title for p in result.items[0].posts] == ["p1", "p2", "p3"]
    assert [p.title for p in result.items[1].posts] == ["p4"]
