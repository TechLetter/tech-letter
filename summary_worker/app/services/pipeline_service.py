from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from langchain_core.language_models.chat_models import BaseChatModel

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_SUMMARY
from common.events.post import (
    EventType,
    PostSummaryRequestedEvent,
    PostSummaryResponseEvent,
)

from ..parser import extract_plain_text, extract_thumbnail
from ..renderer import render_html
from ..summarizer import summarize_post
from ..validator import validate_plain_text


logger = logging.getLogger(__name__)


def handle_post_summary_requested_event(
    requested: PostSummaryRequestedEvent,
    *,
    bus: KafkaEventBus,
    chat_model: BaseChatModel,
) -> None:
    """PostSummaryRequestedEvent 에 대한 전체 파이프라인을 처리한다.

    - HTML 렌더링
    - 본문 텍스트 추출
    - 썸네일 URL 추출
    - LLM 요약
    - PostSummaryResponseEvent 생성 및 publish
    """

    logger.info(
        "handling PostSummaryRequestedEvent id=%s post_id=%s link=%s",
        requested.id,
        requested.post_id,
        requested.link,
    )

    # 1. HTML 렌더링
    try:
        rendered_html = render_html(requested.link)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at render_html for PostSummaryRequestedEvent id=%s post_id=%s link=%s",
            requested.id,
            requested.post_id,
            requested.link,
        )
        raise

    # 2. 본문 텍스트 추출
    try:
        plain_text = extract_plain_text(rendered_html)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at extract_plain_text for PostSummaryRequestedEvent id=%s post_id=%s link=%s",
            requested.id,
            requested.post_id,
            requested.link,
        )
        raise

    # 3. 본문 텍스트 검증
    try:
        validate_plain_text(plain_text)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at validate_plain_text for PostSummaryRequestedEvent id=%s post_id=%s link=%s",
            requested.id,
            requested.post_id,
            requested.link,
        )
        raise

    # 4. 썸네일 URL 추출
    try:
        thumbnail_url = extract_thumbnail(rendered_html, requested.link)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at extract_thumbnail for PostSummaryRequestedEvent id=%s post_id=%s link=%s",
            requested.id,
            requested.post_id,
            requested.link,
        )
        raise

    # 5. AI 요약
    try:
        summary_result = summarize_post(chat_model=chat_model, plain_text=plain_text)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed at summarize_post for PostSummaryRequestedEvent id=%s post_id=%s link=%s",
            requested.id,
            requested.post_id,
            requested.link,
        )
        raise

    # 6. PostSummaryResponse 이벤트 구성 및 publish
    now = datetime.now(timezone.utc).isoformat()
    succeeded_event_id = str(uuid.uuid4())
    succeeded_event = PostSummaryResponseEvent(
        id=succeeded_event_id,
        type=EventType.POST_SUMMARY_RESPONSE,
        timestamp=now,
        source="summary-worker",
        version="1.0",
        post_id=requested.post_id,
        link=requested.link,
        plain_text=plain_text,
        thumbnail_url=thumbnail_url,
        categories=summary_result.categories,
        tags=summary_result.tags,
        summary=summary_result.summary,
        model_name=getattr(chat_model, "model_name", None)
        or getattr(chat_model, "model", "unknown"),
    )

    try:
        out_evt = new_json_event(
            payload=asdict(succeeded_event),
            event_id=succeeded_event_id,
        )
        bus.publish(TOPIC_POST_SUMMARY.base, out_evt)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to publish PostSummaryResponseEvent for request id=%s post_id=%s link=%s",
            requested.id,
            requested.post_id,
            requested.link,
        )
        raise

    logger.info(
        "successfully processed PostSummaryRequestedEvent id=%s post_id=%s link=%s summary_len=%d categories=%s tags=%s model_name=%s",
        requested.id,
        requested.post_id,
        requested.link,
        len(summary_result.summary),
        summary_result.categories,
        summary_result.tags,
        succeeded_event.model_name,
    )
