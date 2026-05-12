from __future__ import annotations

from datetime import datetime

from user_service.app.models.chat_session import (
    ChatMessage,
    ChatRole,
    ChatSession,
    ChatSessionMemory,
)
from user_service.app.services.chat_session_service import ChatSessionService


class FakeChatSessionRepository:
    def __init__(self) -> None:
        self.updated_memory: ChatSessionMemory | None = None

    def update_memory(
        self,
        session_id: str,
        user_code: str,
        memory: ChatSessionMemory,
    ) -> ChatSession:
        self.updated_memory = memory
        return _build_session(message_count=12, memory=memory)


def _build_session(
    *,
    message_count: int,
    memory: ChatSessionMemory | None = None,
) -> ChatSession:
    now = datetime.utcnow()
    return ChatSession(
        id="session-1",
        user_code="user-1",
        title="테스트 세션",
        messages=[
            ChatMessage(
                role=ChatRole.USER if index % 2 == 0 else ChatRole.ASSISTANT,
                content=f"message {index}",
            )
            for index in range(message_count)
        ],
        memory=memory,
        created_at=now,
        updated_at=now,
    )


def test_should_request_memory_compression_when_threshold_is_reached(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHAT_CONTEXT_COMPRESSION_MIN_MESSAGES", "12")
    monkeypatch.setenv("CHAT_CONTEXT_COMPRESSION_BATCH_SIZE", "6")
    service = ChatSessionService(FakeChatSessionRepository())

    assert service.should_request_memory_compression(_build_session(message_count=12))


def test_should_not_request_memory_compression_when_pending(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHAT_CONTEXT_COMPRESSION_MIN_MESSAGES", "12")
    service = ChatSessionService(FakeChatSessionRepository())

    session = _build_session(
        message_count=20,
        memory=ChatSessionMemory(status="pending", covered_message_count=10),
    )

    assert not service.should_request_memory_compression(session)


def test_mark_memory_compression_pending_preserves_existing_summary() -> None:
    repo = FakeChatSessionRepository()
    service = ChatSessionService(repo)
    session = _build_session(
        message_count=20,
        memory=ChatSessionMemory(
            summary="기존 요약",
            covered_message_count=10,
            status="completed",
        ),
    )

    service.mark_memory_compression_pending(session)

    assert repo.updated_memory is not None
    assert repo.updated_memory.summary == "기존 요약"
    assert repo.updated_memory.covered_message_count == 10
    assert repo.updated_memory.status == "pending"
