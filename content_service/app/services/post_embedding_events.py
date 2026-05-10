from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EMBEDDING
from common.events.post import EventType, PostEmbeddingDeleteRequestedEvent


def publish_post_embedding_delete_requested(
    event_bus: KafkaEventBus,
    *,
    post_id: str,
) -> None:
    event_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    evt = PostEmbeddingDeleteRequestedEvent(
        id=event_id,
        type=EventType.POST_EMBEDDING_DELETE_REQUESTED,
        timestamp=timestamp,
        source="content-service",
        version="1.0",
        post_id=post_id,
    )

    payload = asdict(evt)
    wrapped = new_json_event(payload=payload, event_id=event_id)
    event_bus.publish(TOPIC_POST_EMBEDDING.base, wrapped)
