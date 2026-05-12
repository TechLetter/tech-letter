import logging
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import get_kafka_event_bus
from common.eventbus.topics import TOPIC_CHAT, TOPIC_CHAT_CONTEXT_COMPRESSION
from common.events.chat import ChatContextCompressionRequestedEvent, ChatEventType
from common.mongo.client import get_database

from ..repositories.chat_session_repository import ChatSessionRepository
from ..services.chat_session_service import (
    ChatSessionService,
    get_context_compression_min_messages,
)
from ..models.chat_session import ChatRole

logger = logging.getLogger(__name__)


class ChatEventHandler:
    def __init__(self):
        # Service 초기화
        # 주의: 여기서는 DB 커넥션을 새로 맺거나 전역 pool을 사용해야 함.
        # get_database()는 pymongo Client를 반환하므로 OK.
        db = get_database()
        repo = ChatSessionRepository(db)
        self.service = ChatSessionService(repo)
        self.bus = get_kafka_event_bus()
        self._stop_event = threading.Event()

    def handle_chat_completed(self, event_data: Any):
        """chat.completed 이벤트 핸들러."""
        # event_data는 Event 객체일 것임 (KafkaEventBus._decode_event로 디코딩됨)
        # common/eventbus/kafka.py의 subscribe 메서드 확인:
        # handler(evt) 호출함. evt는 Event 객체.

        try:
            # Event 객체에서 payload 추출
            # Event 클래스는 common.eventbus.core.Event
            payload = (
                event_data.payload if hasattr(event_data, "payload") else event_data
            )

            # 만약 payload가 dict가 아니라면 (혹시 모를 상황 대비)
            if not isinstance(payload, dict):
                logger.warning(
                    f"ChatEventHandler: invalid payload type: {type(payload)}"
                )
                return

            event_type = payload.get(
                "type"
            )  # Event.type이 아니라 payload 내부의 type일 수도 있음.
            # 하지만 chat.completed Topic을 구독하므로 type 체크는 크게 중요하지 않을 수 있음.
            # Event 객체 자체에 type이 있을 것임.

            session_id = payload.get("session_id")
            user_code = payload.get("user_code")
            query = payload.get("query")
            answer = payload.get("answer")
            metadata = payload.get("metadata")

            if not session_id:
                # session_id가 없으면 스킵
                return

            logger.info(f"ChatEventHandler: saving messages to session {session_id}")

            # User Message 저장
            if query:
                self.service.add_message(session_id, ChatRole.USER, query)

            # Assistant Message 저장
            saved_session = None
            if answer:
                saved_session = self.service.add_message(
                    session_id,
                    ChatRole.ASSISTANT,
                    answer,
                    metadata if isinstance(metadata, dict) else None,
                )
            if saved_session and self.service.should_request_memory_compression(
                saved_session
            ):
                self.service.mark_memory_compression_pending(saved_session)
                self._publish_context_compression_requested(saved_session)

        except Exception as e:
            logger.error(f"ChatEventHandler: error handling event: {e}", exc_info=True)

    def _publish_context_compression_requested(self, session) -> None:
        if not session.id:
            return
        event_id = str(uuid.uuid4())
        event = ChatContextCompressionRequestedEvent(
            id=event_id,
            type=ChatEventType.CHAT_CONTEXT_COMPRESSION_REQUESTED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="user-service",
            version="1.0",
            user_code=session.user_code,
            session_id=session.id or "",
            message_count=len(session.messages),
            threshold=get_context_compression_min_messages(),
        )
        wrapped = new_json_event(payload=asdict(event), event_id=event_id)
        self.bus.publish(TOPIC_CHAT_CONTEXT_COMPRESSION.base, wrapped)
        logger.info(
            "ChatEventHandler: requested context compression session_id=%s message_count=%d",
            session.id,
            len(session.messages),
        )

    def start_consuming(self):
        """별도 스레드에서 컨슈머 실행."""

        def consume():
            logger.info("ChatEventHandler: starting consumer thread")
            self.bus.subscribe(
                group_id="tech-letter-user-service-chat-consumer",
                topic=TOPIC_CHAT,
                handler=self.handle_chat_completed,
            )

        t = threading.Thread(target=consume, daemon=True)
        t.start()


def run_chat_consumer():
    """챗봇 이벤트 컨슈머 실행."""
    handler = ChatEventHandler()
    handler.start_consuming()
