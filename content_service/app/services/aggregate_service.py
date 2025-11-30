from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EVENTS
from common.events.post import EventType, PostCreatedEvent
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

        # 1차: 블로그 메타데이터 upsert
        for blog_src in config.blogs:
            blog_doc = self._to_blog_model(blog_src)
            try:
                self._blog_repository.upsert_by_rss_url(blog_doc)
            except Exception as exc:  # noqa: BLE001
                logger.error("failed to upsert blog %s: %s", blog_src.name, exc)

        # 2차: 각 블로그의 RSS 피드를 읽어 새 포스트 수집
        for blog_src in config.blogs:
            try:
                self._collect_posts_from_blog(blog_src, config.blog_fetch_batch_size)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to collect posts from blog %s: %s", blog_src.name, exc
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
    ) -> None:
        blog = self._blog_repository.get_by_rss_url(blog_src.rss_url)
        if blog is None:
            logger.error(
                "blog not found after upsert: name=%s rss_url=%s",
                blog_src.name,
                blog_src.rss_url,
            )
            return

        items = fetch_rss_feeds(blog_src.rss_url, limit=batch_size)

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
                self._publish_post_created(post)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "failed to publish PostCreated event (post_id=%s, title=%s): %s",
                    inserted_id,
                    post.title,
                    exc,
                )

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
            rendered_html="",
            aisummary=empty_summary,
        )

    def _publish_post_created(self, post: Post) -> None:
        if post.id is None:
            logger.error("cannot publish PostCreated event: post.id is None")
            return

        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        evt = PostCreatedEvent(
            id=event_id,
            type=EventType.POST_CREATED,
            timestamp=timestamp,
            source=self._source,
            version="1.0",
            post_id=post.id,
            blog_id=post.blog_id,
            blog_name=post.blog_name,
            title=post.title,
            link=post.link,
        )

        payload = asdict(evt)
        wrapped = new_json_event(payload=payload, event_id=event_id)
        self._event_bus.publish(TOPIC_POST_EVENTS.base, wrapped)

        logger.info(
            "published PostCreated event id=%s post_id=%s title=%s",
            event_id,
            post.id,
            post.title,
        )
