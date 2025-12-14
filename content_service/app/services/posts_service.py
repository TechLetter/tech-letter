from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import Depends
from pymongo.database import Database

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus, get_kafka_event_bus
from common.eventbus.topics import TOPIC_POST_EMBEDDING, TOPIC_POST_SUMMARY
from common.events.post import (
    EventType,
    PostEmbeddingRequestedEvent,
    PostSummaryRequestedEvent,
)
from common.models.post import AISummary, ListPostsFilter, Post, StatusFlags
from common.mongo.client import get_database

from ..repositories.interfaces import (
    BlogRepositoryInterface,
    PostRepositoryInterface,
)
from ..repositories.blog_repository import BlogRepository
from ..repositories.post_repository import PostRepository

logger = logging.getLogger(__name__)


class PostsService:
    """포스트 조회/검색 및 관리(CRUD) 비즈니스 로직.

    - Repository(PostRepository)에만 의존하고, Mongo 세부 구현은 알지 않는다.
    - 관리자 기능(생성, 삭제, 상태 변경 등)도 포함한다.
    """

    def __init__(
        self,
        post_repo: PostRepositoryInterface,
        blog_repo: BlogRepositoryInterface,
        event_bus: KafkaEventBus,
    ) -> None:
        self._post_repo = post_repo
        self._blog_repo = blog_repo
        self._event_bus = event_bus

    def list_posts(self, filter_: ListPostsFilter) -> tuple[list[Post], int]:
        return self._post_repo.list(filter_)

    def get_post(self, post_id: str) -> Post | None:
        return self._post_repo.find_by_id(post_id)

    def get_plain_text(self, post_id: str) -> str | None:
        return self._post_repo.get_plain_text(post_id)

    def increment_view_count(self, post_id: str) -> bool:
        return self._post_repo.increment_view_count(post_id)

    def list_by_ids(self, ids: list[str]) -> list[Post]:
        return self._post_repo.list_by_ids(ids)

    def create_post(self, title: str, link: str, blog_id: str) -> Post:
        """수동으로 포스트를 생성하고 요약 이벤트를 발행한다."""
        
        # 1. 블로그 조회
        blog = self._blog_repo.find_by_id(blog_id)
        if not blog:
            raise ValueError(f"blog not found: {blog_id}")

        # 2. 중복 체크
        if self._post_repo.is_exist_by_link(link):
             raise ValueError(f"post with link already exists: {link}")

        # 3. Post 모델 생성
        now = datetime.now(timezone.utc)
        status = StatusFlags(ai_summarized=False)
        empty_summary = AISummary(
            categories=[],
            tags=[],
            summary="",
            model_name="",
            generated_at=now,
        )
        
        post = Post(
            id=None,
            created_at=now,
            updated_at=now,
            status=status,
            view_count=0,
            blog_id=blog.id or blog_id,
            blog_name=blog.name,
            title=title,
            link=link,
            published_at=now, # 수동 생성은 현재 시각을 발행일로 가정
            thumbnail_url="",
            aisummary=empty_summary,
            embedding=None
        )

        # 4. 저장
        inserted_id = self._post_repo.insert(post)
        post.id = inserted_id

        # 5. 이벤트 발행 (요약부터 시작)
        self._publish_summary_requested(post)

        return post

    def delete_post(self, post_id: str) -> bool:
        return self._post_repo.delete_by_id(post_id)

    def trigger_summary(self, post_id: str) -> bool:
        post = self._post_repo.find_by_id(post_id)
        if not post:
            return False
        
        self._publish_summary_requested(post)
        return True

    def trigger_embedding(self, post_id: str) -> bool:
        post = self._post_repo.find_by_id(post_id)
        if not post:
            return False

        self._publish_embedding_requested(post)
        return True

    def _publish_summary_requested(self, post: Post) -> None:
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        evt = PostSummaryRequestedEvent(
            id=event_id,
            type=EventType.POST_SUMMARY_REQUESTED,
            timestamp=timestamp,
            source="content-service-manual",
            version="1.0",
            post_id=post.id,
            title=post.title,
            blog_name=post.blog_name or "Unknown",
            link=post.link,
            published_at=post.published_at.isoformat(),
        )

        payload = asdict(evt)
        wrapped = new_json_event(payload=payload, event_id=event_id)
        self._event_bus.publish(TOPIC_POST_SUMMARY.base, wrapped)

    def _publish_embedding_requested(self, post: Post) -> None:
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # Post에서 aisummary 정보 가져오기
        categories = post.aisummary.categories if post.aisummary else []
        tags = post.aisummary.tags if post.aisummary else []
        summary = post.aisummary.summary if post.aisummary else ""
        
        # plain_text는 별도 조회 필요 (저장소에서)
        plain_text = self._post_repo.get_plain_text(post.id) or ""

        evt = PostEmbeddingRequestedEvent(
            id=event_id,
            type=EventType.POST_EMBEDDING_REQUESTED,
            timestamp=timestamp,
            source="content-service-manual",
            version="1.0",
            post_id=post.id,
            title=post.title,
            blog_name=post.blog_name or "Unknown",
            link=post.link,
            published_at=post.published_at.isoformat(),
            categories=categories,
            tags=tags,
            plain_text=plain_text,
            summary=summary,
        )

        payload = asdict(evt)
        wrapped = new_json_event(payload=payload, event_id=event_id)
        self._event_bus.publish(TOPIC_POST_EMBEDDING.base, wrapped)


def get_posts_service(
    db: Database = Depends(get_database),
    event_bus: KafkaEventBus = Depends(get_kafka_event_bus),
) -> PostsService:
    """FastAPI DI용 PostsService 팩토리."""
    post_repo = PostRepository(db)
    blog_repo = BlogRepository(db)
    return PostsService(post_repo, blog_repo, event_bus)
