from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EMBEDDING
from common.events.post import (
    EventType,
    PostEmbeddingRequestedEvent,
    PostSummaryResponseEvent,
)
from common.models.post import AISummary, Post, StatusFlags

from ..repositories.interfaces import PostRepositoryInterface


logger = logging.getLogger(__name__)


class PostSummaryApplyService:
    """PostSummaryResponseEvent 를 받아 MongoDB Post 문서에 요약 정보를 반영하는 서비스."""

    def __init__(
        self,
        post_repository: PostRepositoryInterface,
        event_bus: KafkaEventBus,
    ) -> None:
        self._post_repository = post_repository
        self._event_bus = event_bus

    def apply(self, event: PostSummaryResponseEvent) -> None:
        """요약 완료 이벤트를 받아 Post 문서에 요약/플래그를 반영한다."""

        post_id = event.post_id
        if not post_id:
            logger.error("PostSummaryResponseEvent has empty post_id: %r", event)
            return

        try:
            post = self._post_repository.find_by_id(post_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to load post for PostSummaryResponseEvent post_id=%s", post_id
            )
            raise

        if post is None:
            logger.warning(
                "post not found for PostSummaryResponseEvent post_id=%s", post_id
            )
            return

        try:
            generated_at = datetime.fromisoformat(event.timestamp)
        except Exception:  # noqa: BLE001
            logger.exception(
                "invalid timestamp on PostSummaryResponseEvent id=%s timestamp=%r, falling back to now",
                event.id,
                event.timestamp,
            )
            generated_at = datetime.now(timezone.utc)

        summary = AISummary(
            categories=event.categories,
            tags=event.tags,
            summary=event.summary or "",
            model_name=event.model_name or "",
            generated_at=generated_at,
        )

        status = post.status
        status.ai_summarized = True

        updates = {
            "plain_text": event.plain_text or "",
            "thumbnail_url": event.thumbnail_url or "",
            "aisummary": summary.model_dump(by_alias=True),
            "status": status.model_dump(by_alias=True),
        }

        try:
            self._post_repository.update_fields(post_id, updates)
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to update post with summary for post_id=%s id=%s",
                post_id,
                event.id,
            )
            raise

        logger.info(
            "applied PostSummaryResponseEvent id=%s to post_id=%s (model=%s)",
            event.id,
            post_id,
            event.model_name,
        )

        # 요약 저장 성공 후 임베딩 파이프라인 트리거
        self._publish_embedding_requested(
            post=post,
            event=event,
        )

    def _publish_embedding_requested(
        self,
        post: Post,
        event: PostSummaryResponseEvent,
    ) -> None:
        """임베딩 파이프라인을 트리거하기 위해 PostEmbeddingRequestedEvent를 발행한다."""

        embedding_event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        embedding_event = PostEmbeddingRequestedEvent(
            id=embedding_event_id,
            type=EventType.POST_EMBEDDING_REQUESTED,
            timestamp=now,
            source="content-service",
            version="1.0",
            post_id=event.post_id,
            title=post.title,
            blog_name=post.blog_name,
            link=event.link,
            published_at=post.published_at.isoformat(),
            categories=event.categories,
            tags=event.tags,
            plain_text=event.plain_text,
            summary=event.summary,
        )

        try:
            out_evt = new_json_event(
                payload=asdict(embedding_event),
                event_id=embedding_event_id,
            )
            self._event_bus.publish(TOPIC_POST_EMBEDDING.base, out_evt)
            logger.info(
                "published PostEmbeddingRequestedEvent id=%s post_id=%s",
                embedding_event_id,
                event.post_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to publish PostEmbeddingRequestedEvent for post_id=%s (non-fatal)",
                event.post_id,
            )
