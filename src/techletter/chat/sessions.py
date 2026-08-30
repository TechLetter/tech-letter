"""대화 세션 관리."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from techletter.chat.models import DEFAULT_TITLE, ChatMessage, ChatSession, SessionMemory
from techletter.chat.models import title_from as _title_from
from techletter.core.errors import ChatSessionNotFoundError
from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.repositories import ChatSessionRepository, SessionSummary
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

    async def list(self, user_code: str, page: Page) -> tuple[list[SessionSummary], int]:
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

    # ── 메모리 압축 ────────────────────────────────────────────────
    def needs_compression(self, session: ChatSession) -> bool:
        """대화가 길어져 요약이 필요한지 본다.

        `pending`이면 이미 잡이 돌고 있으니 다시 걸지 않는다. 마지막 압축
        이후 쌓인 메시지가 배치 크기를 넘어야 한다.
        """
        count = len(session.messages)
        if count < self._settings.compression_min_messages:
            return False
        memory = session.memory
        if memory and memory.status == "pending":
            return False
        covered = memory.covered_message_count if memory else 0
        return count - covered >= self._settings.compression_batch_size

    async def claim_compression(self, session_id: str) -> bool:
        return await self._sessions.claim_compression(session_id)

    async def store_summary(
        self, session_id: str, summary: str, covered_message_count: int
    ) -> None:
        await self._sessions.set_memory(
            session_id,
            SessionMemory(
                summary=summary,
                covered_message_count=max(0, covered_message_count),
                status="completed",
                updated_at=utcnow(),
            ),
        )

    async def mark_compression_failed(
        self, session_id: str, reason: str, previous: SessionMemory | None
    ) -> None:
        """실패를 기록하되 **직전 요약은 보존한다**.

        요약을 지우면 다음 대화가 맥락을 통째로 잃는다.
        """
        await self._sessions.set_memory(
            session_id,
            SessionMemory(
                summary=previous.summary if previous else "",
                covered_message_count=previous.covered_message_count if previous else 0,
                status="failed",
                requested_at=previous.requested_at if previous else None,
                updated_at=utcnow(),
                error_message=reason[:300],
            ),
        )
