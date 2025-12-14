from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from common.eventbus.config import get_brokers, get_group_id
from common.eventbus.core import Event
from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EMBEDDING
from common.events.post import (
    EventType,
    PostEmbedResponseEvent,
    PostEmbeddingAppliedEvent,
)

from ..vector_store import VectorStore


logger = logging.getLogger(__name__)


def _handle_event(evt: Event, *, vector_store: VectorStore, bus: KafkaEventBus) -> None:
    payload = evt.payload
    if not isinstance(payload, dict):
        logger.error("unexpected payload type for event %s: %r", evt.id, type(payload))
        return

    event_type = str(payload.get("type", ""))
    if event_type != EventType.POST_EMBEDDING_RESPONSE:
        # 다른 타입의 이벤트는 이 핸들러의 책임이 아니므로 무시한다.
        logger.debug(
            "ignoring non-PostEmbedResponse event: type=%s id=%s", event_type, evt.id
        )
        return

    logger.info(
        "received PostEmbedResponseEvent id=%s post_id=%s",
        evt.id,
        payload.get("post_id"),
    )

    try:
        embed_response = PostEmbedResponseEvent.from_dict(payload)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to decode PostEmbedResponseEvent id=%s payload=%r",
            payload.get("id"),
            payload,
        )
        raise

    # Vector DB에 upsert
    try:
        upsert_result = vector_store.upsert_post_embeddings(embed_response)
        logger.info(
            "upserted %d chunks to vector store for post_id=%s model_name=%s",
            upsert_result.chunk_count,
            embed_response.post_id,
            embed_response.model_name,
        )

        now = datetime.now(timezone.utc).isoformat()
        applied_event_id = str(uuid.uuid4())
        applied_event = PostEmbeddingAppliedEvent(
            id=applied_event_id,
            type=EventType.POST_EMBEDDING_APPLIED,
            timestamp=now,
            source="chatbot-service",
            version="1.0",
            post_id=embed_response.post_id,
            model_name=embed_response.model_name,
            collection_name=upsert_result.collection_name,
            vector_dimension=upsert_result.vector_dimension,
            chunk_count=upsert_result.chunk_count,
        )

        out_evt = new_json_event(
            payload=asdict(applied_event), event_id=applied_event_id
        )
        bus.publish(TOPIC_POST_EMBEDDING.base, out_evt)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to upsert embeddings for post_id=%s",
            embed_response.post_id,
        )
        raise


def run_embed_consumer(stop_flag: list[bool], vector_store: VectorStore) -> None:
    """PostEmbedResponseEvent를 소비하여 Vector DB에 upsert하는 구독 루프를 실행한다."""

    logger.info("embed-consumer starting up")

    brokers = get_brokers()
    group_id = get_group_id()

    bus = KafkaEventBus(brokers)

    try:
        logger.info(
            "subscribing to topic=%s group_id=%s", TOPIC_POST_EMBEDDING.base, group_id
        )
        bus.subscribe(
            group_id=group_id,
            topic=TOPIC_POST_EMBEDDING,
            handler=lambda evt: _handle_event(evt, vector_store=vector_store, bus=bus),
            stop_flag=stop_flag,
        )
    finally:
        bus.close()
        logger.info("embed-consumer stopped")
