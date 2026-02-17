from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Generator

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
from ..renderer import BaseRenderer
from ..summarizer import summarize_post
from ..validator import validate_plain_text


logger = logging.getLogger(__name__)


@contextmanager
def _log_step(
    step_name: str,
    requested: PostSummaryRequestedEvent,
) -> Generator[None, None, None]:
    """파이프라인 단계별 예외를 일관되게 로깅하는 컨텍스트 매니저."""
    try:
        yield
    except Exception:
        logger.exception(
            "failed at %s for PostSummaryRequestedEvent id=%s post_id=%s link=%s",
            step_name,
            requested.id,
            requested.post_id,
            requested.link,
        )
        raise


def handle_post_summary_requested_event(
    requested: PostSummaryRequestedEvent,
    *,
    bus: KafkaEventBus,
    chat_model: BaseChatModel,
    renderer: BaseRenderer,
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
    with _log_step("renderer.render", requested):
        rendered_html = renderer.render(requested.link)

    # 2. 본문 텍스트 추출
    with _log_step("extract_plain_text", requested):
        plain_text = extract_plain_text(rendered_html)

    # 3. 본문 텍스트 검증
    with _log_step("validate_plain_text", requested):
        validate_plain_text(plain_text)

    # 4. 썸네일 URL 추출 (실패해도 파이프라인 중단하지 않음)
    thumbnail_url = ""
    try:
        thumbnail_url = extract_thumbnail(rendered_html, requested.link)
    except Exception:
        logger.warning(
            "extract_thumbnail failed for PostSummaryRequestedEvent id=%s post_id=%s link=%s — proceeding with empty thumbnail",
            requested.id,
            requested.post_id,
            requested.link,
            exc_info=True,
        )

    # 5. AI 요약
    with _log_step("summarize_post", requested):
        summary_result = summarize_post(chat_model=chat_model, plain_text=plain_text)

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

    with _log_step("publish_event", requested):
        out_evt = new_json_event(
            payload=asdict(succeeded_event),
            event_id=succeeded_event_id,
        )
        bus.publish(TOPIC_POST_SUMMARY.base, out_evt)

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
