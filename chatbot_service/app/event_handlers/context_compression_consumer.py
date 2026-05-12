from __future__ import annotations

import logging
from typing import Any

from common.eventbus.config import get_brokers
from common.eventbus.core import Event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_CHAT_CONTEXT_COMPRESSION
from common.events.chat import (
    ChatContextCompressionRequestedEvent,
    ChatEventType,
)

from ..services.conversation_memory import ConversationMessage
from ..services.rag_service import RAGService
from ..services.user_session_client import UserSessionClient


logger = logging.getLogger(__name__)


def _handle_context_compression_event(
    evt: Event,
    *,
    rag_service: RAGService,
    user_session_client: UserSessionClient,
) -> None:
    payload = evt.payload
    if not isinstance(payload, dict):
        logger.warning("invalid context compression payload type: %r", type(payload))
        return

    event_type = payload.get("type")
    if event_type != ChatEventType.CHAT_CONTEXT_COMPRESSION_REQUESTED:
        logger.debug("ignoring non-compression event type=%s", event_type)
        return

    request_event = ChatContextCompressionRequestedEvent.from_dict(payload)
    logger.info(
        "processing context compression request session_id=%s user_code=%s message_count=%d",
        request_event.session_id,
        request_event.user_code,
        request_event.message_count,
    )

    previous_summary = ""
    previous_covered_message_count = 0
    try:
        session = user_session_client.get_session(
            user_code=request_event.user_code,
            session_id=request_event.session_id,
        )
        memory = session.get("memory")
        if isinstance(memory, dict):
            previous_summary = str(memory.get("summary") or "")
            previous_covered_message_count = int(
                memory.get("covered_message_count") or 0
            )
        messages = _extract_messages(session.get("messages", []))
        summary, covered_message_count = rag_service.compress_session_context(messages)
        user_session_client.update_memory(
            user_code=request_event.user_code,
            session_id=request_event.session_id,
            summary=summary,
            covered_message_count=covered_message_count,
            status="completed",
        )
        logger.info(
            "context compression completed session_id=%s covered_message_count=%d",
            request_event.session_id,
            covered_message_count,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "context compression failed session_id=%s", request_event.session_id
        )
        try:
            user_session_client.update_memory(
                user_code=request_event.user_code,
                session_id=request_event.session_id,
                summary=previous_summary,
                covered_message_count=previous_covered_message_count,
                status="failed",
                error_message=str(exc),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to mark context compression failed session_id=%s",
                request_event.session_id,
            )
        raise


def _extract_messages(raw_messages: Any) -> list[ConversationMessage]:
    if not isinstance(raw_messages, list):
        return []

    messages: list[ConversationMessage] = []
    for raw_message in raw_messages:
        if not isinstance(raw_message, dict):
            continue
        role = str(raw_message.get("role", ""))
        content = str(raw_message.get("content", ""))
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append(
            ConversationMessage(
                role=role,
                content=content,
                created_at=raw_message.get("created_at"),
            )
        )
    return messages


def run_context_compression_consumer(
    stop_flag: list[bool],
    rag_service: RAGService,
    user_session_client: UserSessionClient | None = None,
) -> None:
    logger.info("context-compression-consumer starting up")

    bus = KafkaEventBus(get_brokers())
    client = user_session_client or UserSessionClient.from_env()
    try:
        bus.subscribe(
            group_id="tech-letter-chatbot-context-compression-consumer",
            topic=TOPIC_CHAT_CONTEXT_COMPRESSION,
            handler=lambda evt: _handle_context_compression_event(
                evt,
                rag_service=rag_service,
                user_session_client=client,
            ),
            stop_flag=stop_flag,
        )
    finally:
        bus.close()
        logger.info("context-compression-consumer stopped")
