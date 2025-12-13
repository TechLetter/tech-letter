from __future__ import annotations

import logging
import signal

from common.eventbus.config import get_brokers, get_group_id
from common.eventbus.core import Event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EMBEDDING
from common.events.post import EventType, PostEmbeddingRequestedEvent
from common.logger import setup_logger
from common.mongo.client import get_database

from .cache import EmbeddingCache
from .config import load_config
from .embedder import TextEmbedder
from .services.pipeline_service import handle_post_embedding_requested_event


logger = logging.getLogger(__name__)


def _handle_event(
    evt: Event,
    *,
    bus: KafkaEventBus,
    embedder: TextEmbedder,
    cache: EmbeddingCache,
) -> None:
    payload = evt.payload
    if not isinstance(payload, dict):
        logger.error("unexpected payload type for event %s: %r", evt.id, type(payload))
        return

    event_type = str(payload.get("type", ""))
    if event_type != EventType.POST_EMBEDDING_REQUESTED:
        # 다른 타입의 이벤트는 이 워커의 책임이 아니므로 무시한다.
        return

    try:
        requested = PostEmbeddingRequestedEvent.from_dict(payload)
    except Exception:
        logger.exception(
            "failed to decode PostEmbeddingRequestedEvent id=%s payload=%r",
            payload.get("id"),
            payload,
        )
        raise

    handle_post_embedding_requested_event(
        requested=requested,
        bus=bus,
        embedder=embedder,
        cache=cache,
    )


def main() -> None:
    setup_logger()
    logger.info("embedding-worker (python) starting up")

    brokers = get_brokers()
    group_id = get_group_id()

    bus = KafkaEventBus(brokers)

    app_cfg = load_config()
    embedder = TextEmbedder(
        embedding_config=app_cfg.embedding,
        chunk_config=app_cfg.chunk,
    )

    db = get_database()
    cache = EmbeddingCache(db)

    stop_flag = [False]

    def _signal_handler(signum, frame) -> None:  # type: ignore[unused-argument]
        logger.info("received signal %s, shutting down embedding-worker...", signum)
        stop_flag[0] = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        bus.subscribe(
            group_id=group_id,
            topic=TOPIC_POST_EMBEDDING,
            handler=lambda evt: _handle_event(
                evt, bus=bus, embedder=embedder, cache=cache
            ),
            stop_flag=stop_flag,
        )
    finally:
        bus.close()


if __name__ == "__main__":  # pragma: no cover
    main()
