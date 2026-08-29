"""chat 도메인 잡 핸들러."""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.core.errors import PermanentError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.memory import MemoryBuilder
    from techletter.chat.repositories import ChatSessionRepository
    from techletter.chat.sessions import ChatSessionService
    from techletter.core.jobs.models import Job

__all__ = ["CompressionRequestedHandler"]

logger = get_logger(__name__)


class CompressionRequestedHandler:
    """`chat.compression_requested` 처리 — 오래된 대화를 요약해 저장한다."""

    def __init__(
        self,
        sessions: ChatSessionService,
        repository: ChatSessionRepository,
        memory: MemoryBuilder,
    ) -> None:
        self._sessions = sessions
        self._repository = repository
        self._memory = memory

    async def __call__(self, job: Job) -> None:
        session_id = str(job.payload.get("session_id") or "")
        if not session_id:
            raise PermanentError("compression job without session_id", reason="bad_payload")

        # 소유자 확인 없이 읽는다. 잡을 만든 쪽이 이미 확인했고, 여기서는
        # 세션 id만 들고 온다.
        session = await self._repository.get(session_id)
        if session is None:
            # 대화가 지워졌다. 재시도해도 의미 없다.
            raise PermanentError(f"chat session not found: {session_id}", reason="session_deleted")

        previous = session.memory
        try:
            summary, covered = await self._memory.summarize(session.messages)
        except Exception as exc:
            # 상태만 failed로 바꾸고 **직전 요약은 남긴다**. 요약을 지우면
            # 다음 대화가 맥락을 통째로 잃는다.
            await self._sessions.mark_compression_failed(session_id, str(exc), previous)
            raise

        await self._sessions.store_summary(session_id, summary, covered)
        logger.info(
            "conversation compressed",
            extra={"session_id": session_id, "covered": covered},
        )
