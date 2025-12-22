"""크레딧 관련 이벤트 정의."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Self


class CreditEventType:
    """크레딧 이벤트 타입 상수."""

    CREDIT_CONSUMED = "credit.consumed"
    CREDIT_GRANTED = "credit.granted"


@dataclass(slots=True)
class CreditConsumedEvent:
    """크레딧 소비 이벤트.

    채팅 요청 시 크레딧이 차감되면 발행된다.
    """

    id: str
    type: str
    timestamp: str
    source: str
    version: str
    user_code: str
    credit_expired_at: str
    amount: int
    remaining: int
    reason: str
    session_id: str | None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            user_code=str(data["user_code"]),
            credit_expired_at=str(data["credit_expired_at"]),
            amount=int(data["amount"]),
            remaining=int(data["remaining"]),
            reason=str(data["reason"]),
            session_id=data.get("session_id"),
        )


@dataclass(slots=True)
class CreditGrantedEvent:
    """크레딧 부여 이벤트.

    관리자가 크레딧을 부여하면 발행된다.
    """

    id: str
    type: str
    timestamp: str
    source: str
    version: str
    user_code: str
    credit_expired_at: str
    amount: int
    remaining: int
    reason: str
    granted_by: str  # 부여한 관리자

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            user_code=str(data["user_code"]),
            credit_expired_at=str(data["credit_expired_at"]),
            amount=int(data["amount"]),
            remaining=int(data["remaining"]),
            reason=str(data["reason"]),
            granted_by=str(data["granted_by"]),
        )
