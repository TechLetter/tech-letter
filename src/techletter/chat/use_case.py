"""채팅 한 번의 처리 흐름.

순서가 전부다:

1. **입력 가드** — 크레딧을 깎기 전에 본다. 정책 위반이면 사용자는 잔액을
   잃지 않는다.
2. **세션 확보** — 없으면 만든다.
3. **차감** — 원자적으로. 부족하면 402.
4. **에이전트 실행**
5. **기록 / 환불** — 실패하면 되돌린다. 클라이언트가 끊어도 마찬가지다.

5번이 `asyncio.shield` 안에 있는 이유: 스트리밍 중 브라우저를 닫으면 요청
태스크가 취소된다. 그때 차감만 남고 환불이 안 되면 사용자는 답도 못 받고
크레딧만 잃는다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from techletter.chat.guards import PromptGuard
from techletter.core.errors import (
    InvalidRequestError,
    LlmRateLimitedError,
    LlmUnavailableError,
    PolicyBlockedError,
    QuotaExceededError,
    RetryableError,
)
from techletter.core.llm.model_events import known_model_ids
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from bson import ObjectId
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.chat.agent import Activity, ChatAgent
    from techletter.chat.memory import MemoryBuilder
    from techletter.chat.models import ChatSession
    from techletter.chat.sessions import ChatSessionService
    from techletter.core.jobs.queue import JobQueue
    from techletter.settings import ChatSettings
    from techletter.users.credits import CreditService

__all__ = ["ChatAnswer", "ChatUseCase"]

logger = get_logger(__name__)


@dataclass(slots=True)
class ChatAnswer:
    session_id: str
    message_id: str
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    agent: dict[str, Any] = field(default_factory=dict)
    guard: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    consumed_credits: int = 0
    remaining_credits: int = 0


class ChatUseCase:
    def __init__(
        self,
        *,
        sessions: ChatSessionService,
        credits: CreditService,
        memory: MemoryBuilder,
        agent: ChatAgent,
        queue: JobQueue,
        settings: ChatSettings,
        prompt_guard: PromptGuard | None = None,
        catalog_db: AsyncDatabase | None = None,
    ) -> None:
        self._sessions = sessions
        self._credits = credits
        self._memory = memory
        self._agent = agent
        self._queue = queue
        self._settings = settings
        self._guard = prompt_guard or PromptGuard()
        self._catalog_db = catalog_db

    async def run(
        self,
        *,
        user_code: str,
        query: str,
        session_id: str | None = None,
        on_activity: Callable[[Activity], Awaitable[None]] | None = None,
        model_id: str | None = None,
    ) -> ChatAnswer:
        guard = self._guard.inspect(query)
        if guard.blocked:
            raise PolicyBlockedError(guard.message, details={"findings": guard.to_metadata()})
        safe_query = guard.text
        selected_model_id = await self._validated_model_id(model_id)

        session, is_new = await self._resolve_session(user_code, session_id, safe_query)
        consumed = await self._credits.consume(user_code, self._settings.credits_per_message)

        try:
            context = await self._memory.build(safe_query, session.messages, session.memory)
            if selected_model_id is None:
                result = await self._agent.run(safe_query, context, on_activity)
            else:
                result = await self._agent.run(
                    safe_query, context, on_activity, model_id=selected_model_id
                )
        except BaseException as exc:
            # 취소(브라우저 종료)도 여기로 온다. 환불은 반드시 끝까지 돌린다.
            await asyncio.shield(self._refund(user_code, consumed.credit_ids, type(exc).__name__))
            # 라우터는 잡 큐에서도 쓰이므로 JobError를 그대로 던진다. HTTP 채팅
            # 경계에서만 공개용 AppError로 바꿔, 환불이 끝난 뒤 원인을 노출한다.
            if isinstance(exc, QuotaExceededError):
                raise LlmRateLimitedError() from exc
            if isinstance(exc, RetryableError):
                raise LlmUnavailableError() from exc
            raise

        return await asyncio.shield(
            self._record(
                session=session,
                query=safe_query,
                query_already_stored=is_new,
                guard_metadata=guard.to_metadata() if guard.action != "pass" else result.guard,
                memory_metadata=context.to_metadata(),
                result=result,
                consumed=consumed.consumed,
                remaining=consumed.remaining,
            )
        )

    async def _validated_model_id(self, model_id: str | None) -> str | None:
        """무료 카탈로그에 있는 사용자 모델만 답변 후보에 넣는다."""
        if model_id is None:
            return None

        db = self._catalog_db if self._catalog_db is not None else self._session_database()
        if db is None:
            # 테스트 대역이나 아직 조립되지 않은 경계에서는 카탈로그를 읽을
            # 수 없으므로 요청을 막지 않고 기존 자동 라우팅을 유지한다.
            return None
        known = await known_model_ids(db)
        if not known:
            # DB 장애·초기 빈 카탈로그에서는 유료 id를 추측해 허용하지 않고,
            # 사용자의 선택만 버린 채 무료 자동 후보로 계속 답한다.
            return None
        if model_id not in known:
            raise InvalidRequestError(
                "선택한 모델을 사용할 수 없습니다.", details={"field": "model_id"}
            )
        return model_id

    def _session_database(self) -> AsyncDatabase | None:
        """세션 저장소가 이미 쥔 DB를 모델 카탈로그 검증에도 재사용한다."""
        repository = getattr(self._sessions, "_sessions", None)
        collection = getattr(repository, "_col", None)
        database = getattr(collection, "database", None)
        return database

    async def _resolve_session(
        self, user_code: str, session_id: str | None, query: str
    ) -> tuple[ChatSession, bool]:
        """(세션, 첫 질문이 이미 담겼는지)를 준다."""
        if session_id:
            return await self._sessions.get(session_id, user_code), False
        # 새 세션은 첫 질문을 함께 넣으며 제목도 그것으로 정한다.
        return await self._sessions.create(user_code, query), True

    async def _refund(self, user_code: str, credit_ids: list[ObjectId], reason: str) -> None:
        try:
            await self._credits.refund(user_code, credit_ids, f"chat_failed:{reason}")
        except Exception:
            # 환불 실패로 원래 오류를 덮지 않는다. 로그로 남겨 사람이 처리한다.
            logger.exception("credit refund failed", extra={"user_code": user_code})

    async def _record(
        self,
        *,
        session: ChatSession,
        query: str,
        query_already_stored: bool,
        guard_metadata: dict[str, Any],
        memory_metadata: dict[str, Any],
        result: Any,
        consumed: int,
        remaining: int,
    ) -> ChatAnswer:
        session_id = str(session.id)
        # 새 세션은 생성할 때 첫 질문을 이미 담았다. 두 번 넣지 않는다.
        if not query_already_stored:
            session = await self._sessions.append(session, "user", query)

        agent_metadata = {
            "mode": "agent",
            "intent": result.intent,
            "activities": result.activities,
            "model_id": result.model_id,
        }
        session = await self._sessions.append(
            session,
            "assistant",
            result.answer,
            metadata={
                "sources": result.sources,
                "agent": agent_metadata,
                "guard": guard_metadata,
                "memory": memory_metadata,
            },
        )
        await self._maybe_compress(session)

        return ChatAnswer(
            session_id=session_id,
            message_id=f"{session_id}:{len(session.messages) - 1}",
            answer=result.answer,
            sources=result.sources,
            agent=agent_metadata,
            guard=guard_metadata,
            memory=memory_metadata,
            consumed_credits=consumed,
            remaining_credits=remaining,
        )

    async def _maybe_compress(self, session: ChatSession) -> None:
        """대화가 길어지면 요약 잡을 건다. 답변을 막지 않는다."""
        from techletter.core.jobs.types import JobType  # noqa: PLC0415

        if not self._sessions.needs_compression(session):
            return
        session_id = str(session.id)
        if not await self._sessions.claim_compression(session_id):
            return
        await self._queue.enqueue(
            JobType.CHAT_COMPRESSION_REQUESTED,
            session_id,
            {"session_id": session_id, "user_code": session.user_code},
        )
