from __future__ import annotations

import logging
import signal
from typing import List

from common.eventbus.config import get_brokers, get_group_id
from common.eventbus.core import Event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EVENTS
from common.events.post import EventType, PostSummarizedEvent
from common.mongo.client import get_database

from ..repositories.post_repository import PostRepository
from ..services.post_summary_apply_service import PostSummaryApplyService


logger = logging.getLogger(__name__)


def _handle_event(evt: Event, *, service: PostSummaryApplyService) -> None:
    payload = evt.payload
    if not isinstance(payload, dict):
        logger.error("unexpected payload type for event %s: %r", evt.id, type(payload))
        return

    event_type = str(payload.get("type", ""))
    if event_type != EventType.POST_SUMMARIZED:
        # 다른 타입의 이벤트는 이 핸들러의 책임이 아니므로 무시한다.
        logger.debug(
            "ignoring non-PostSummarized event: type=%s id=%s", event_type, evt.id
        )
        return

    logger.info(
        "received PostSummarizedEvent id=%s post_id=%s", evt.id, payload.get("post_id")
    )

    try:
        summarized = PostSummarizedEvent.from_dict(payload)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to decode PostSummarizedEvent id=%s payload=%r",
            payload.get("id"),
            payload,
        )
        raise

    service.apply(summarized)


def run_post_summary_consumer(stop_flag: List[bool]) -> None:
    """PostSummarizedEvent 를 계속 소비하는 구독 루프를 실행한다.

    - stop_flag[0] 이 True 가 되면 안전하게 루프를 종료한다.
    - FastAPI lifespan 스레드나 단독 프로세스(main) 양쪽에서 재사용 가능하다.
    """
    logger.info("post-summary-consumer starting up")

    db = get_database()
    post_repo = PostRepository(db)
    service = PostSummaryApplyService(post_repository=post_repo)

    brokers = get_brokers()
    group_id = get_group_id()

    bus = KafkaEventBus(brokers)

    try:
        logger.info(
            "subscribing to topic=%s group_id=%s", TOPIC_POST_EVENTS.base, group_id
        )
        bus.subscribe(
            group_id=group_id,
            topic=TOPIC_POST_EVENTS,
            handler=lambda evt: _handle_event(evt, service=service),
            stop_flag=stop_flag,
        )
    finally:
        bus.close()
        logger.info("post-summary-consumer stopped")


def main() -> None:
    """단독 프로세스로 실행할 때 사용하는 엔트리 포인트."""

    logging.basicConfig(level=logging.INFO)
    logger.info("content-service post-summary-consumer starting up")

    stop_flag: List[bool] = [False]

    def _signal_handler(signum, frame) -> None:  # type: ignore[unused-argument]
        logger.info(
            "received signal %s, shutting down post-summary-consumer...", signum
        )
        stop_flag[0] = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    run_post_summary_consumer(stop_flag)


if __name__ == "__main__":  # pragma: no cover
    main()
