from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from chatbot_service.app.event_handlers.context_compression_consumer import (
    _handle_context_compression_event,
)
from common.eventbus.core import Event
from common.events.chat import ChatContextCompressionRequestedEvent, ChatEventType


class FakeRAGService:
    def __init__(self) -> None:
        self.raise_error: Exception | None = None
        self.received_message_count = 0

    def compress_session_context(self, messages):
        self.received_message_count = len(messages)
        if self.raise_error is not None:
            raise self.raise_error
        return "압축 요약", max(0, len(messages) - 8)


class FakeUserSessionClient:
    def __init__(self) -> None:
        self.session = {
            "memory": {
                "summary": "기존 요약",
                "covered_message_count": 10,
                "status": "pending",
            },
            "messages": [
                {"role": "user", "content": f"질문 {index}"}
                for index in range(12)
            ],
        }
        self.updated_memory: dict | None = None

    def get_session(self, *, user_code: str, session_id: str):
        return self.session

    def update_memory(
        self,
        *,
        user_code: str,
        session_id: str,
        summary: str,
        covered_message_count: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        self.updated_memory = {
            "summary": summary,
            "covered_message_count": covered_message_count,
            "status": status,
            "error_message": error_message,
        }


def _build_event() -> Event:
    payload = ChatContextCompressionRequestedEvent(
        id="compression-1",
        type=ChatEventType.CHAT_CONTEXT_COMPRESSION_REQUESTED,
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="user-service",
        version="1.0",
        user_code="user-1",
        session_id="session-1",
        message_count=12,
        threshold=12,
    )
    return Event(id=payload.id, payload=asdict(payload))


def test_context_compression_consumer_updates_completed_memory() -> None:
    rag_service = FakeRAGService()
    user_session_client = FakeUserSessionClient()

    _handle_context_compression_event(
        _build_event(),
        rag_service=rag_service,
        user_session_client=user_session_client,
    )

    assert rag_service.received_message_count == 12
    assert user_session_client.updated_memory == {
        "summary": "압축 요약",
        "covered_message_count": 4,
        "status": "completed",
        "error_message": None,
    }


def test_context_compression_consumer_preserves_previous_summary_on_failure() -> None:
    rag_service = FakeRAGService()
    rag_service.raise_error = RuntimeError("llm failed")
    user_session_client = FakeUserSessionClient()

    with pytest.raises(RuntimeError):
        _handle_context_compression_event(
            _build_event(),
            rag_service=rag_service,
            user_session_client=user_session_client,
        )

    assert user_session_client.updated_memory == {
        "summary": "기존 요약",
        "covered_message_count": 10,
        "status": "failed",
        "error_message": "llm failed",
    }
