from __future__ import annotations

import logging

from common.eventbus.config import get_brokers, get_group_id
from common.eventbus.core import Event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EMBEDDING
from common.events.post import EventType, PostEmbeddingAppliedEvent
from common.mongo.client import get_database

from ..repositories.post_repository import PostRepository
from ..services.post_embedding_apply_service import PostEmbeddingApplyService


logger = logging.getLogger(__name__)


def _handle_event(evt: Event, *, service: PostEmbeddingApplyService) -> None:
    payload = evt.payload
    if not isinstance(payload, dict):
        logger.error("unexpected payload type for event %s: %r", evt.id, type(payload))
        return

    event_type = str(payload.get("type", ""))
    if event_type != EventType.POST_EMBEDDING_APPLIED:
        # 다른 타입의 이벤트는 이 컨슈머의 책임이 아니므로 무시한다.
        return

    logger.info(
        "received PostEmbeddingAppliedEvent id=%s post_id=%s",
        evt.id,
        payload.get("post_id"),
    )

    try:
        applied = PostEmbeddingAppliedEvent.from_dict(payload)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to decode PostEmbeddingAppliedEvent id=%s payload=%r",
            payload.get("id"),
            payload,
        )
        raise

    service.apply(applied)


def run_post_embedding_consumer(stop_flag: list[bool]) -> None:
    logger.info("post-embedding-consumer starting up")

    brokers = get_brokers()
    group_id = get_group_id()

    bus = KafkaEventBus(brokers)

    db = get_database()
    post_repo = PostRepository(db)
    service = PostEmbeddingApplyService(post_repository=post_repo)

    try:
        logger.info(
            "subscribing to topic=%s group_id=%s", TOPIC_POST_EMBEDDING.base, group_id
        )
        bus.subscribe(
            group_id=group_id,
            topic=TOPIC_POST_EMBEDDING,
            handler=lambda evt: _handle_event(evt, service=service),
            stop_flag=stop_flag,
        )
    finally:
        bus.close()
        logger.info("post-embedding-consumer stopped")
