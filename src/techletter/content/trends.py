"""주간 기술 흐름.

최근 7일과 직전 7일을 주제별로 비교한다. 순위는 **다룬 회사 수**로 매긴다 —
글 수로 매기면 글을 많이 내는 한 회사(AWS 블로그 한 곳이 한 달에 16건)가
그대로 1위가 된다. 여러 회사가 같이 다룬 주제가 흐름에 가깝다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from techletter.core.time import utcnow
from techletter.summary.topics import OTHER

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from techletter.content.models import Post
    from techletter.content.repositories import PostRepository, TopicActivity

__all__ = ["TopicTrend", "TrendsService", "WeeklyTrends", "pick_representatives"]

WINDOW = timedelta(days=7)
REPRESENTATIVES = 3


@dataclass(frozen=True, slots=True)
class TopicTrend:
    topic: str
    blog_count: int
    post_count: int
    previous_blog_count: int
    previous_post_count: int
    posts: list[Post] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class WeeklyTrends:
    from_at: datetime
    to: datetime
    previous_from: datetime
    previous_to: datetime
    post_count: int
    blog_count: int
    items: list[TopicTrend]


def pick_representatives(recent: list[tuple[str, str]], limit: int = REPRESENTATIVES) -> list[str]:
    """최근 글부터 고르되 회사가 겹치지 않게 한다. 모자라면 겹쳐도 채운다.

    `recent`는 (post_id, blog_name)을 최근 순으로 담는다.
    """
    picked: list[str] = []
    seen_blogs: set[str] = set()
    for post_id, blog in recent:
        if blog not in seen_blogs:
            picked.append(post_id)
            seen_blogs.add(blog)
        if len(picked) == limit:
            return picked
    for post_id, _ in recent:
        if post_id not in picked:
            picked.append(post_id)
        if len(picked) == limit:
            break
    return picked


class TrendsService:
    def __init__(self, posts: PostRepository) -> None:
        self._posts = posts

    async def weekly(self, limit: int, now: datetime | None = None) -> WeeklyTrends:
        to = now or utcnow()
        from_at = to - WINDOW
        previous_from = from_at - WINDOW

        current = await self._posts.topic_activity(from_at, to)
        previous = {
            row.topic: row for row in await self._posts.topic_activity(previous_from, from_at)
        }
        totals = await self._posts.activity_totals(from_at, to)

        rows = [row for row in current if row.topic != OTHER]
        rows.sort(key=lambda row: (-row.blog_count, -row.post_count, row.topic))
        rows = rows[: max(1, limit)]

        picks = {row.topic: pick_representatives(row.recent) for row in rows}
        found = await self._posts.get_many([pid for ids in picks.values() for pid in ids])

        return WeeklyTrends(
            from_at=from_at,
            to=to,
            previous_from=previous_from,
            previous_to=from_at,
            post_count=totals[0],
            blog_count=totals[1],
            items=[
                TopicTrend(
                    topic=row.topic,
                    blog_count=row.blog_count,
                    post_count=row.post_count,
                    previous_blog_count=_blogs(previous.get(row.topic)),
                    previous_post_count=_posts(previous.get(row.topic)),
                    posts=[found[pid] for pid in picks[row.topic] if pid in found],
                )
                for row in rows
            ],
        )


def _blogs(row: TopicActivity | None) -> int:
    return row.blog_count if row else 0


def _posts(row: TopicActivity | None) -> int:
    return row.post_count if row else 0
