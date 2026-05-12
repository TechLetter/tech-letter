"""채팅 관련 이벤트 정의."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Self


class ChatEventType:
    """채팅 이벤트 타입 상수."""

    CHAT_COMPLETED = "chat.completed"
    CHAT_FAILED = "chat.failed"
    CHAT_CONTEXT_COMPRESSION_REQUESTED = "chat.context_compression.requested"


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
    metadata: dict[str, Any] | None = None

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
            metadata=data.get("metadata"),
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


@dataclass(slots=True)
class ChatContextCompressionRequestedEvent:
    """채팅 세션 컨텍스트 압축 요청 이벤트."""

    id: str
    type: str
    timestamp: str
    source: str
    version: str
    user_code: str
    session_id: str
    message_count: int
    threshold: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            user_code=str(data["user_code"]),
            session_id=str(data["session_id"]),
            message_count=int(data.get("message_count", 0)),
            threshold=int(data.get("threshold", 0)),
        )
