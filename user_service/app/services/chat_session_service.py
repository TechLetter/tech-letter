import os
from datetime import datetime
from typing import Any, Optional

from common.schemas.pagination import PaginatedResponse
from ..models.chat_session import (
    ChatSession,
    ChatMessage,
    ChatSessionMemory,
    ChatRole,
)
from ..repositories.chat_session_repository import ChatSessionRepository


class ChatSessionService:
    def __init__(self, repo: ChatSessionRepository):
        self.repo = repo

    def create_session(
        self, user_code: str, first_message: Optional[str] = None
    ) -> ChatSession:
        """새로운 대화 세션을 생성한다. 첫 메시지가 있으면 제목을 자동 생성한다."""
        title = "New Chat"
        messages = []

        if first_message:
            # 제목은 첫 30자 + ...
            title = (
                first_message[:30] + "..." if len(first_message) > 30 else first_message
            )
            messages.append(ChatMessage(role=ChatRole.USER, content=first_message))

        session = ChatSession(
            user_code=user_code,
            title=title,
            messages=messages,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        return self.repo.create(session)

    def get_session(self, session_id: str, user_code: str) -> Optional[ChatSession]:
        return self.repo.get_by_id(session_id, user_code)

    def list_sessions(
        self, user_code: str, page: int, page_size: int
    ) -> PaginatedResponse[ChatSession]:
        items, total = self.repo.list_sessions(user_code, page, page_size)
        return PaginatedResponse(
            total=total, page=page, page_size=page_size, items=items
        )

    def delete_session(self, session_id: str, user_code: str) -> bool:
        return self.repo.delete(session_id, user_code)

    def add_message(
        self,
        session_id: str,
        role: ChatRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Optional[ChatSession]:
        """세션에 메시지를 추가한다.

        첫 user 메시지이고 title이 'New Chat'인 경우 제목을 자동 생성한다.
        """
        # 현재 세션 조회
        # Note: session_id만으로 조회 (user_code 검증은 이벤트 핸들러에서 신뢰)
        current = self.repo.get_by_id_only(session_id)

        if not current:
            return None

        # 첫 user 메시지이고 title이 "New Chat"인 경우 제목 자동 생성
        if (
            role == ChatRole.USER
            and current.title == "New Chat"
            and len(current.messages) == 0
        ):
            new_title = content[:30] + "..." if len(content) > 30 else content
            self.repo.update_title(session_id, new_title)

        message = ChatMessage(role=role, content=content, metadata=metadata)
        return self.repo.add_message(session_id, message)

    def should_request_memory_compression(self, session: ChatSession) -> bool:
        message_count = len(session.messages)
        threshold = get_context_compression_min_messages()
        batch_size = get_context_compression_batch_size()

        if message_count < threshold:
            return False

        memory = session.memory
        if memory and memory.status == "pending":
            return False

        covered_message_count = memory.covered_message_count if memory else 0
        return message_count - covered_message_count >= batch_size

    def mark_memory_compression_pending(self, session: ChatSession) -> ChatSession | None:
        now = datetime.utcnow()
        existing_memory = session.memory
        memory = ChatSessionMemory(
            summary=existing_memory.summary if existing_memory else "",
            covered_message_count=(
                existing_memory.covered_message_count if existing_memory else 0
            ),
            status="pending",
            requested_at=now,
            updated_at=existing_memory.updated_at if existing_memory else None,
            error_message=None,
        )
        if session.id is None:
            return None
        return self.repo.update_memory(session.id, session.user_code, memory)

    def update_memory(
        self,
        session_id: str,
        user_code: str,
        summary: str,
        covered_message_count: int,
        status: str = "completed",
        error_message: str | None = None,
    ) -> Optional[ChatSession]:
        memory = ChatSessionMemory(
            summary=summary,
            covered_message_count=max(0, covered_message_count),
            status=status,
            updated_at=datetime.utcnow(),
            error_message=error_message,
        )
        return self.repo.update_memory(session_id, user_code, memory)


def get_context_compression_min_messages() -> int:
    return _get_positive_int("CHAT_CONTEXT_COMPRESSION_MIN_MESSAGES", 12)


def get_context_compression_batch_size() -> int:
    return _get_positive_int("CHAT_CONTEXT_COMPRESSION_BATCH_SIZE", 6)


def _get_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default
