from __future__ import annotations

import logging
import signal
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from common.eventbus.config import get_brokers, get_group_id
from common.eventbus.core import Event
from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EVENTS
from common.events.post import EventType, PostCreatedEvent, PostSummarizedEvent
from common.llm.factory import create_chat_model

from .config import load_chat_model_config
from .renderer import render_html
from .parser import extract_plain_text, extract_thumbnail
from .summarizer import summarize_post


logger = logging.getLogger(__name__)


def _handle_event(evt: Event, *, bus: KafkaEventBus, chat_model: Any) -> None:
    payload = evt.payload
    if not isinstance(payload, dict):
        logger.error("unexpected payload type for event %s: %r", evt.id, type(payload))
        return

    event_type = str(payload.get("type", ""))
    if event_type != EventType.POST_CREATED:
        # 다른 타입의 이벤트는 이 워커의 책임이 아니므로 무시한다.
        return

    try:
        created = PostCreatedEvent.from_dict(payload)
    except Exception:
        logger.exception(
            "failed to decode PostCreatedEvent id=%s payload=%r",
            payload.get("id"),
            payload,
        )
        raise

    logger.info(
        "handling PostCreatedEvent id=%s post_id=%s link=%s",
        created.id,
        created.post_id,
        created.link,
    )

    # 1. HTML 렌더링
    try:
        rendered_html = render_html(created.link)
    except Exception:
        logger.exception(
            "failed at render_html for PostCreatedEvent id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    # 2. 본문 텍스트 추출
    try:
        plain_text = extract_plain_text(rendered_html)
    except Exception:
        logger.exception(
            "failed at extract_plain_text for PostCreatedEvent id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    # 3. 썸네일 URL 추출
    try:
        thumbnail_url = extract_thumbnail(rendered_html, created.link)
    except Exception:
        logger.exception(
            "failed at extract_thumbnail for PostCreatedEvent id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    # 4. AI 요약
    try:
        summary_result = summarize_post(chat_model=chat_model, plain_text=plain_text)
    except Exception:
        logger.exception(
            "failed at summarize_post for PostCreatedEvent id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    # 5. PostSummarized 이벤트 구성 (Aggregate가 DB 저장) 및 publish
    now = datetime.now(timezone.utc).isoformat()
    summarized_event = PostSummarizedEvent(
        id=created.id,
        type=EventType.POST_SUMMARIZED,
        timestamp=now,
        source="summary-worker",
        version="1.0",
        post_id=created.post_id,
        link=created.link,
        rendered_html=rendered_html,
        thumbnail_url=thumbnail_url,
        categories=summary_result.categories,
        tags=summary_result.tags,
        summary=summary_result.summary,
        model_name=getattr(chat_model, "model_name", "unknown"),
    )

    try:
        out_evt = new_json_event(payload=asdict(summarized_event))
        bus.publish(TOPIC_POST_EVENTS.base, out_evt)
    except Exception:
        logger.exception(
            "failed to publish PostSummarizedEvent for original id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    logger.info(
        "successfully processed PostCreatedEvent id=%s post_id=%s link=%s summary_len=%d categories=%s tags=%s",
        created.id,
        created.post_id,
        created.link,
        len(summary_result.summary),
        summary_result.categories,
        summary_result.tags,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("summary-worker (python) starting up")

    brokers = get_brokers()
    group_id = get_group_id()

    bus = KafkaEventBus(brokers)

    chat_cfg = load_chat_model_config()
    chat_model = create_chat_model(chat_cfg)

    stop_flag = [False]

    def _signal_handler(signum, frame) -> None:  # type: ignore[unused-argument]
        logger.info("received signal %s, shutting down summary-worker...", signum)
        stop_flag[0] = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        bus.subscribe(
            group_id=group_id,
            topic=TOPIC_POST_EVENTS,
            handler=lambda evt: _handle_event(evt, bus=bus, chat_model=chat_model),
            stop_flag=stop_flag,
        )
    finally:
        bus.close()


if __name__ == "__main__":  # pragma: no cover
    main()
