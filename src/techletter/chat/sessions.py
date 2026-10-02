"""대화 세션 관리."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from techletter.chat.models import DEFAULT_TITLE, ChatMessage, ChatSession
from techletter.chat.models import title_from as _title_from
from techletter.core.errors import ChatSessionNotFoundError
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.repositories import ChatSessionRepository
    from techletter.core.pagination import Page
    from techletter.settings import ChatSettings

__all__ = ["ChatSessionService"]

logger = get_logger(__name__)


class ChatSessionService:
    def __init__(self, sessions: ChatSessionRepository, settings: ChatSettings) -> None:
        self._sessions = sessions
        self._settings = settings

    async def create(self, user_code: str, first_message: str | None = None) -> ChatSession:
        return await self._sessions.create(ChatSession.start(user_code, first_message))

    async def get(self, session_id: str, user_code: str) -> ChatSession:
        session = await self._sessions.get(session_id, user_code)
        if session is None:
            raise ChatSessionNotFoundError(f"chat session not found: {session_id}")
        return session

    async def list(self, user_code: str, page: Page) -> tuple[list[ChatSession], int]:
        return await self._sessions.list_sessions(user_code, page)

    async def delete(self, session_id: str, user_code: str) -> None:
        if not await self._sessions.delete(session_id, user_code):
            raise ChatSessionNotFoundError(f"chat session not found: {session_id}")

    async def delete_all(self, user_code: str) -> int:
        return await self._sessions.delete_by_user(user_code)

    async def append(
        self,
        session: ChatSession,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatSession:
        """메시지를 붙인다. 첫 사용자 메시지면 제목도 정한다."""
        if role == "user" and session.title == DEFAULT_TITLE and not session.messages:
            await self._sessions.set_title(str(session.id), _title_from(content))

        message = ChatMessage(role=role, content=content, metadata=metadata, created_at=utcnow())  # type: ignore[arg-type]
        updated = await self._sessions.append_message(str(session.id), message)
        if updated is None:
            raise ChatSessionNotFoundError(f"chat session not found: {session.id}")
        return updated
