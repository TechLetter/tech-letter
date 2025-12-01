from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EVENTS
from common.events.post import EventType, PostCreatedEvent, PostSummarizedEvent

from ..parser import extract_plain_text, extract_thumbnail
from ..renderer import render_html
from ..summarizer import summarize_post
from ..validator import validate_plain_text


logger = logging.getLogger(__name__)


def handle_post_created_event(
    created: PostCreatedEvent,
    *,
    bus: KafkaEventBus,
    chat_model: Any,
) -> None:
    """PostCreatedEvent 에 대한 전체 파이프라인을 처리한다.

    - HTML 렌더링
    - 본문 텍스트 추출
    - 썸네일 URL 추출
    - LLM 요약
    - PostSummarizedEvent 생성 및 publish
    """

    logger.info(
        "handling PostCreatedEvent id=%s post_id=%s link=%s",
        created.id,
        created.post_id,
        created.link,
    )

    # 1. HTML 렌더링
    try:
        rendered_html = render_html(created.link)
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at extract_plain_text for PostCreatedEvent id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    # 3. 본문 텍스트 검증
    try:
        validate_plain_text(plain_text)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at validate_plain_text for PostCreatedEvent id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    # 4. 썸네일 URL 추출
    try:
        thumbnail_url = extract_thumbnail(rendered_html, created.link)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at extract_thumbnail for PostCreatedEvent id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    # 5. AI 요약
    try:
        summary_result = summarize_post(chat_model=chat_model, plain_text=plain_text)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at summarize_post for PostCreatedEvent id=%s post_id=%s link=%s",
            created.id,
            created.post_id,
            created.link,
        )
        raise

    # 6. PostSummarized 이벤트 구성 및 publish
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
    except Exception:  # noqa: BLE001
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
