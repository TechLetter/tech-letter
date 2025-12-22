import logging
import threading
from typing import Any

from common.eventbus.kafka import get_kafka_event_bus
from common.eventbus.topics import TOPIC_CHAT
from common.mongo.client import get_database

from ..repositories.chat_session_repository import ChatSessionRepository
from ..services.chat_session_service import ChatSessionService
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

            if not session_id:
                # session_id가 없으면 스킵
                return

            logger.info(f"ChatEventHandler: saving messages to session {session_id}")

            # User Message 저장
            if query:
                self.service.add_message(session_id, ChatRole.USER, query)

            # Assistant Message 저장
            if answer:
                self.service.add_message(session_id, ChatRole.ASSISTANT, answer)

        except Exception as e:
            logger.error(f"ChatEventHandler: error handling event: {e}", exc_info=True)

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
