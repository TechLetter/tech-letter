"""chat 도메인 문서 모델.

DB 필드명은 기존 그대로다(제약 C1). `memory.status`의 값도 저장된 문자열
(`none`/`pending`/`completed`/`failed`)을 유지하고, 04 §3.6의 `ready` 표기는
DTO에서만 쓴다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from techletter.core.db.documents import BaseDocument, MongoDateTime, SubDocument
from techletter.core.time import utcnow

__all__ = [
    "DEFAULT_TITLE",
    "ChatMessage",
    "ChatRole",
    "ChatSession",
    "MemoryStatus",
    "SessionMemory",
    "SuggestedQuestion",
    "title_from",
]

ChatRole = Literal["user", "assistant"]
MemoryStatus = Literal["none", "pending", "completed", "failed"]

DEFAULT_TITLE = "New Chat"
TITLE_MAX_CHARS = 30


def title_from(first_message: str) -> str:
    """첫 질문에서 제목을 만든다. 30자를 넘으면 잘라 `...`을 붙인다(현행과 동일)."""
    text = first_message.strip()
    if not text:
        return DEFAULT_TITLE
    return f"{text[:TITLE_MAX_CHARS]}..." if len(text) > TITLE_MAX_CHARS else text


class ChatMessage(SubDocument):
    """대화 한 줄. `chat_sessions.messages[]`의 원소다.

    기존 문서에 `created_at`만 있고 `updated_at`은 없다. 메시지는 고쳐 쓰지
    않으니 그대로 둔다.
    """

    role: ChatRole = "user"
    content: str = ""
    created_at: MongoDateTime = Field(default_factory=utcnow)
    metadata: dict[str, Any] | None = None
    """`sources`/`agent`/`guard`/`memory`. DTO에서는 평탄화한다(04 §3.5)."""


class SessionMemory(SubDocument):
    """`chat_sessions.memory`. 압축된 대화 요약."""

    summary: str = ""
    covered_message_count: int = 0
    status: MemoryStatus = "none"
    requested_at: MongoDateTime | None = None
    updated_at: MongoDateTime | None = None
    error_message: str | None = None


class ChatSession(BaseDocument):
    user_code: str = ""
    title: str = DEFAULT_TITLE
    messages: list[ChatMessage] = Field(default_factory=list)
    memory: SessionMemory | None = None

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @classmethod
    def start(cls, user_code: str, first_message: str | None = None) -> ChatSession:
        now = utcnow()
        messages = (
            [ChatMessage(role="user", content=first_message, created_at=now)]
            if first_message
            else []
        )
        return cls(
            user_code=user_code,
            title=title_from(first_message) if first_message else DEFAULT_TITLE,
            messages=messages,
            created_at=now,
            updated_at=now,
        )


class SuggestedQuestion(BaseDocument):
    text: str = ""
    normalized_text: str = ""
    """중복 검사용 키. 유니크 인덱스가 걸린다(05 §1.4)."""
    sort_order: int = 0
    is_active: bool = True
