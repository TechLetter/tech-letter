"""채팅 관련 이벤트 정의."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Self


class ChatEventType:
    """채팅 이벤트 타입 상수."""

    CHAT_COMPLETED = "chat.completed"
    CHAT_FAILED = "chat.failed"


@dataclass(slots=True)
class ChatCompletedEvent:
    """채팅 완료 이벤트.

    AI 호출이 성공하면 발행된다.
    """

    id: str
    type: str
    timestamp: str
    source: str
    version: str
    user_code: str
    session_id: str | None
    query: str
    answer: str
    credit_consumed_id: str
    credit_expired_at: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            user_code=str(data["user_code"]),
            session_id=data.get("session_id"),
            query=str(data["query"]),
            answer=str(data["answer"]),
            credit_consumed_id=str(data["credit_consumed_id"]),
            credit_expired_at=str(data["credit_expired_at"]),
        )


@dataclass(slots=True)
class ChatFailedEvent:
    """채팅 실패 이벤트.

    AI 호출이 실패하면 발행된다. 크레딧 환불 트리거용.
    """

    id: str
    type: str
    timestamp: str
    source: str
    version: str
    user_code: str
    session_id: str | None
    query: str
    error_code: str
    credit_consumed_id: str
    credit_expired_at: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            user_code=str(data["user_code"]),
            session_id=data.get("session_id"),
            query=str(data["query"]),
            error_code=str(data["error_code"]),
            credit_consumed_id=str(data["credit_consumed_id"]),
            credit_expired_at=str(data["credit_expired_at"]),
        )
