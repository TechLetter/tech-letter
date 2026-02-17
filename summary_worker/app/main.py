from __future__ import annotations

import logging
import signal
from functools import partial

from langchain_core.language_models.chat_models import BaseChatModel

from common.eventbus.config import get_brokers, get_group_id
from common.eventbus.core import Event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_SUMMARY
from common.events.post import EventType, PostSummaryRequestedEvent
from common.llm.factory import create_chat_model
from common.logger import setup_logger

from .config import load_config
from .renderer import BaseRenderer, get_renderer
from .services.pipeline_service import handle_post_summary_requested_event


logger = logging.getLogger(__name__)


def _handle_event(
    evt: Event,
    *,
    bus: KafkaEventBus,
    chat_model: BaseChatModel,
    renderer: BaseRenderer,
) -> None:
    payload = evt.payload
    if not isinstance(payload, dict):
        logger.error("unexpected payload type for event %s: %r", evt.id, type(payload))
        return

    event_type = str(payload.get("type", ""))
    if event_type != EventType.POST_SUMMARY_REQUESTED:
        # 다른 타입의 이벤트는 이 워커의 책임이 아니므로 무시한다.
        return

    try:
        requested = PostSummaryRequestedEvent.from_dict(payload)
    except Exception:
        logger.exception(
            "failed to decode PostSummaryRequestedEvent id=%s payload=%r",
            payload.get("id"),
            payload,
        )
        raise

    handle_post_summary_requested_event(
        requested=requested,
        bus=bus,
        chat_model=chat_model,
        renderer=renderer,
    )


def main() -> None:
    setup_logger()
    logger.info("summary-worker (python) starting up")

    brokers = get_brokers()
    group_id = get_group_id()

    bus = KafkaEventBus(brokers)

    app_cfg = load_config()
    chat_model = create_chat_model(app_cfg.llm)
    renderer = get_renderer(app_cfg)

    logger.info("renderer strategy: %s", app_cfg.renderer_strategy)

    stop_flag = [False]

    def _signal_handler(signum, frame) -> None:  # type: ignore[unused-argument]
        logger.info("received signal %s, shutting down summary-worker...", signum)
        stop_flag[0] = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    handler = partial(
        _handle_event, bus=bus, chat_model=chat_model, renderer=renderer,
    )

    try:
        bus.subscribe(
            group_id=group_id,
            topic=TOPIC_POST_SUMMARY,
            handler=handler,
            stop_flag=stop_flag,
        )
    finally:
        bus.close()


if __name__ == "__main__":  # pragma: no cover
    main()
