from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_SUMMARY
from common.events.post import EventType, PostSummaryRequestedEvent
from common.models.blog import Blog
from common.models.post import AISummary, Post, StatusFlags

from ..config import AggregateConfig, BlogSourceConfig
from ..repositories.interfaces import BlogRepositoryInterface, PostRepositoryInterface
from ..rss.feeder import RssFeedItem, fetch_rss_feeds


logger = logging.getLogger(__name__)


class AggregateService:
    """RSS 피드에서 블로그/포스트를 수집하고 PostCreated 이벤트를 발행하는 서비스.

    - Go `AggregateService` 의 RunFeedCollection / collectPostsFromBlog 역할을 담당한다.
    - BlogRepository / PostRepository / KafkaEventBus 에만 의존하며, FastAPI 와는 분리된다.
    """

    def __init__(
        self,
        blog_repository: BlogRepositoryInterface,
        post_repository: PostRepositoryInterface,
        event_bus: KafkaEventBus,
        *,
        source: str = "content-service",
    ) -> None:
        self._blog_repository = blog_repository
        self._post_repository = post_repository
        self._event_bus = event_bus
        self._source = source

    def run_feed_collection(self, config: AggregateConfig) -> None:
        """설정된 모든 블로그에 대해 RSS 피드를 수집하고 새 포스트를 저장/이벤트 발행한다."""

        if not config.blogs:
            logger.warning("no blogs configured under aggregate.blogs")
            return

        total_blogs = len(config.blogs)
        logger.info("starting feed collection for %d blogs", total_blogs)

        # 1차: 블로그 메타데이터 upsert
        for idx, blog_src in enumerate(config.blogs, 1):
            logger.debug("upserting blog %d/%d: %s", idx, total_blogs, blog_src.name)
            blog_doc = self._to_blog_model(blog_src)
            try:
                self._blog_repository.upsert_by_rss_url(blog_doc)
            except Exception as exc:  # noqa: BLE001
                logger.error("failed to upsert blog %s: %s", blog_src.name, exc)

        # 2차: 각 블로그의 RSS 피드를 읽어 새 포스트 수집
        total_new_posts = 0
        for idx, blog_src in enumerate(config.blogs, 1):
            logger.info(
                "collecting posts from blog %d/%d: %s", idx, total_blogs, blog_src.name
            )
            try:
                new_posts = self._collect_posts_from_blog(
                    blog_src, config.blog_fetch_batch_size
                )
                total_new_posts += new_posts
                logger.info("collected %d new posts from %s", new_posts, blog_src.name)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to collect posts from blog %s: %s", blog_src.name, exc
                )

        logger.info(
            "feed collection completed: %d new posts from %d blogs",
            total_new_posts,
            total_blogs,
        )

    def _to_blog_model(self, src: BlogSourceConfig) -> Blog:
        now = datetime.now(timezone.utc)
        return Blog(
            id=None,
            created_at=now,
            updated_at=now,
            name=src.name,
            url=src.url,
            rss_url=src.rss_url,
            blog_type=src.blog_type or "company",
        )

    def _collect_posts_from_blog(
        self, blog_src: BlogSourceConfig, batch_size: int
    ) -> int:
        """블로그에서 포스트를 수집하고 신규 포스트 개수를 반환한다."""
        blog = self._blog_repository.get_by_rss_url(blog_src.rss_url)
        if blog is None:
            logger.error(
                "blog not found after upsert: name=%s rss_url=%s",
                blog_src.name,
                blog_src.rss_url,
            )
            return 0

        items = fetch_rss_feeds(blog_src.rss_url, limit=batch_size)
        logger.debug("fetched %d RSS items from %s", len(items), blog_src.name)

        new_post_count = 0
        for item in items:
            if not item.link:
                continue

            try:
                exists = self._post_repository.is_exist_by_link(item.link)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to check post existence (blog=%s, link=%s): %s",
                    blog_src.name,
                    item.link,
                    exc,
                )
                continue

            if exists:
                continue

            post = self._build_post_model(blog, item)

            try:
                inserted_id = self._post_repository.insert(post)
                new_post_count += 1
                logger.debug(
                    "inserted new post: title=%s link=%s", item.title, item.link
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to insert post (blog=%s, title=%s): %s",
                    blog_src.name,
                    item.title,
                    exc,
                )
                continue

            post.id = inserted_id

            try:
                self._publish_post_summary_requested(post)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to publish post summary requested event (post_id=%s, title=%s): %s",
                    inserted_id,
                    post.title,
                    exc,
                )

        return new_post_count

    def _build_post_model(self, blog: Blog, item: RssFeedItem) -> Post:
        now = datetime.now(timezone.utc)

        status = StatusFlags(ai_summarized=False)
        empty_summary = AISummary(
            categories=[],
            tags=[],
            summary="",
            model_name="",
            generated_at=now,
        )

        published_at = item.published_at or now

        return Post(
            id=None,
            created_at=now,
            updated_at=now,
            status=status,
            view_count=0,
            blog_id=blog.id or "",
            blog_name=blog.name,
            title=item.title,
            link=item.link,
            published_at=published_at,
            thumbnail_url="",
            aisummary=empty_summary,
        )

    def _publish_post_summary_requested(self, post: Post) -> None:
        if post.id is None:
            logger.error("cannot publish PostSummaryRequested event: post.id is None")
            return

        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        evt = PostSummaryRequestedEvent(
            id=event_id,
            type=EventType.POST_SUMMARY_REQUESTED,
            timestamp=timestamp,
            source=self._source,
            version="1.0",
            post_id=post.id,
            link=post.link,
        )

        payload = asdict(evt)
        wrapped = new_json_event(payload=payload, event_id=event_id)
        self._event_bus.publish(TOPIC_POST_SUMMARY.base, wrapped)

        logger.info(
            "published PostSummaryRequested event id=%s post_id=%s link=%s",
            event_id,
            post.id,
            post.link,
        )
