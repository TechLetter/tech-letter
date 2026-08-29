"""채팅 DTO (04 §3.5, §3.6).

메시지 메타데이터를 `metadata` 중첩이 아니라 **평탄화**해서 내보낸다.
`memory.status`는 DB의 `none`/`completed`를 계약의 `ready`로 바꾼다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from techletter.core.time import to_iso_z

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.models import ChatMessage, ChatSession, SuggestedQuestion
    from techletter.chat.use_case import ChatAnswer

__all__ = [
    "ChatAnswerOut",
    "ChatMessageOut",
    "ChatSessionOut",
    "MessageIn",
    "SuggestedQuestionIn",
    "SuggestedQuestionOut",
    "memory_status",
]

# DB에 남아 있는 값 → 계약이 정한 값. `none`은 "아직 압축한 적 없음"이고
# `completed`는 "요약이 준비됨"인데, 프론트가 보기에는 둘 다 "정상"이다.
_MEMORY_STATUS = {"none": "ready", "completed": "ready", "pending": "pending", "failed": "failed"}


def memory_status(raw: str | None) -> str:
    return _MEMORY_STATUS.get(raw or "none", "ready")


class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: str | None
    sources: list[dict[str, Any]] | None = None
    agent: dict[str, Any] | None = None
    guard: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None

    @classmethod
    def of(cls, message: ChatMessage) -> ChatMessageOut:
        metadata = message.metadata or {}
        memory = metadata.get("memory")
        if isinstance(memory, dict):
            memory = {**memory, "status": memory_status(memory.get("status"))}
        return cls(
            role=message.role,
            content=message.content,
            created_at=to_iso_z(message.created_at),
            sources=metadata.get("sources"),
            agent=metadata.get("agent"),
            guard=metadata.get("guard"),
            memory=memory,
        )


class ChatSessionOut(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: str | None
    updated_at: str | None
    messages: list[ChatMessageOut] | None = None

    @classmethod
    def of(cls, session: ChatSession, *, with_messages: bool = True) -> ChatSessionOut:
        return cls(
            id=str(session.id),
            title=session.title,
            message_count=len(session.messages),
            created_at=to_iso_z(session.created_at),
            updated_at=to_iso_z(session.updated_at),
            messages=[ChatMessageOut.of(m) for m in session.messages] if with_messages else None,
        )
        # user_code 는 내보내지 않는다 — 자기 세션만 조회한다(04 §3.5).

    @classmethod
    def summary(cls, session: ChatSession, message_count: int) -> ChatSessionOut:
        """목록 항목. 본문 없이 개수만 준다."""
        return cls(
            id=str(session.id),
            title=session.title,
            message_count=message_count,
            created_at=to_iso_z(session.created_at),
            updated_at=to_iso_z(session.updated_at),
            messages=None,
        )


class MessageIn(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ChatAnswerOut(BaseModel):
    session_id: str
    message_id: str
    answer: str
    sources: list[dict[str, Any]]
    agent: dict[str, Any]
    guard: dict[str, Any]
    memory: dict[str, Any]
    credits: dict[str, int]

    @classmethod
    def of(cls, answer: ChatAnswer) -> ChatAnswerOut:
        memory = {**answer.memory, "status": memory_status(answer.memory.get("status"))}
        return cls(
            session_id=answer.session_id,
            message_id=answer.message_id,
            answer=answer.answer,
            sources=answer.sources,
            agent=answer.agent,
            guard=answer.guard or {"action": "pass", "risk_level": "low", "findings": []},
            memory=memory,
            # 정수 두 개(consumed_credits/remaining_credits) → 객체 하나.
            credits={"consumed": answer.consumed_credits, "remaining": answer.remaining_credits},
        )


class SuggestedQuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    sort_order: int | None = None
    is_active: bool = True


class SuggestedQuestionOut(BaseModel):
    id: str
    text: str
    sort_order: int
    is_active: bool

    @classmethod
    def of(cls, question: SuggestedQuestion) -> SuggestedQuestionOut:
        return cls(
            id=str(question.id),
            text=question.text,
            sort_order=question.sort_order,
            is_active=question.is_active,
        )

    @classmethod
    def public(cls, question: SuggestedQuestion) -> dict[str, str]:
        """공개 응답은 id와 text만 준다(04 §4.3)."""
        return {"id": str(question.id), "text": question.text}
