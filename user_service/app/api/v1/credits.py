"""크레딧 관련 내부 API 라우터 (1:N 모델).

Gateway에서 호출하는 내부 API.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from pymongo.database import Database

from common.mongo.client import get_database
from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import get_kafka_event_bus
from common.eventbus.topics import TOPIC_CREDIT, TOPIC_CHAT
from common.events.credit import CreditEventType, CreditConsumedEvent
from common.events.chat import ChatEventType, ChatCompletedEvent, ChatFailedEvent
from common.schemas.pagination import PaginatedResponse

from ...services.credit_service import CreditService, get_credit_service
from ...repositories.user_repository import UserRepository
from ...repositories.interfaces import UserRepositoryInterface
from ...repositories.credit_repository import (
    CreditRepository,
    CreditTransactionRepository,
)


router = APIRouter(prefix="/credits", tags=["credits"])


# -------- Dependencies --------


def get_user_repository(
    db: Database = Depends(get_database),
) -> UserRepositoryInterface:
    """FastAPI DI용 UserRepository 팩토리."""
    return UserRepository(db)


# -------- Request / Response Schemas --------


class ConsumeRequest(BaseModel):
    """크레딧 소비 요청."""

    amount: int = 1
    reason: str = "chat"


class ConsumeResponse(BaseModel):
    """크레딧 소비 결과."""

    remaining: int
    consume_id: str  # 이벤트 추적용 ID
    consumed_credit_ids: list[str]


class CreditSummaryResponse(BaseModel):
    """유저 크레딧 집계 결과."""

    total_remaining: int
    credits: list["CreditItemResponse"]


class CreditItemResponse(BaseModel):
    """개별 크레딧 정보."""

    id: str | None
    amount: int
    original_amount: int
    source: str
    reason: str
    expired_at: str


class GrantDailyResponse(BaseModel):
    """일일 크레딧 지급 결과."""

    granted: int
    already_granted: bool


class GrantRequest(BaseModel):
    """관리자 크레딧 부여 요청."""

    amount: int
    source: str = "admin"
    reason: str
    expired_at: str  # ISO8601


class CreditTransactionResponse(BaseModel):
    """크레딧 트랜잭션 응답."""

    id: str | None
    type: str
    amount: int
    reason: str
    credit_id: str | None
    created_at: str


class LogChatRequest(BaseModel):
    """채팅 로그 요청."""

    consume_id: str
    consumed_credit_ids: list[str]
    query: str
    success: bool
    answer: str | None = None
    error_code: str | None = None
    session_id: str | None = None


class LogChatResponse(BaseModel):
    """채팅 로그 응답."""

    event_id: str
    refunded: bool = False


# -------- Endpoints --------


@router.get("/{user_code}")
def get_credits(
    user_code: str,
    credit_service: Annotated[CreditService, Depends(get_credit_service)],
) -> CreditSummaryResponse:
    """유저의 유효한 크레딧 조회 (집계)."""
    summary = credit_service.get_summary(user_code)
    return CreditSummaryResponse(
        total_remaining=summary.total_remaining,
        credits=[
            CreditItemResponse(
                id=c.id,
                amount=c.amount,
                original_amount=c.original_amount,
                source=c.source,
                reason=c.reason,
                expired_at=c.expired_at.isoformat(),
            )
            for c in summary.credits
        ],
    )


@router.post("/{user_code}/grant-daily")
def grant_daily_credits(
    user_code: str,
    credit_service: Annotated[CreditService, Depends(get_credit_service)],
    user_repo: Annotated[UserRepositoryInterface, Depends(get_user_repository)],
) -> GrantDailyResponse:
    """일일 크레딧 지급 (로그인 시 호출)."""
    user = user_repo.find_by_user_code(user_code)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Identity Hash 생성 (SHA256(provider:sub))
    raw_id = f"{user.provider}:{user.provider_sub}"
    identity_hash = hashlib.sha256(raw_id.encode()).hexdigest()

    granted = credit_service.grant_daily(user_code, identity_hash)
    return GrantDailyResponse(
        granted=granted,
        already_granted=(granted == 0),
    )


@router.post("/{user_code}/consume")
def consume_credits(
    user_code: str,
    req: ConsumeRequest,
    credit_service: Annotated[CreditService, Depends(get_credit_service)],
) -> ConsumeResponse:
    """크레딧 소비 및 credit.consumed 이벤트 발행. 잔액 부족 시 402."""
    result = credit_service.consume(user_code, req.amount, req.reason)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"code": "insufficient_credits", "message": "크레딧이 부족합니다."},
        )
    consumed_ids, remaining = result

    # credit.consumed 이벤트 발행
    consume_id = str(uuid.uuid4())
    _publish_credit_consumed_event(
        user_code=user_code,
        consume_id=consume_id,
        consumed_credit_ids=consumed_ids,
        amount=req.amount,
        remaining=remaining,
        reason=req.reason,
    )

    return ConsumeResponse(
        remaining=remaining,
        consume_id=consume_id,
        consumed_credit_ids=consumed_ids,
    )


@router.post("/{user_code}/log-chat")
def log_chat(
    user_code: str,
    req: LogChatRequest,
    credit_service: Annotated[CreditService, Depends(get_credit_service)],
) -> LogChatResponse:
    """채팅 완료/실패 이벤트 발행. 실패 시 환불도 처리."""
    refunded = False

    if req.success:
        event_id = _publish_chat_completed_event(
            user_code=user_code,
            consume_id=req.consume_id,
            query=req.query,
            answer=req.answer or "",
            session_id=req.session_id,
        )
    else:
        # 채팅 실패 시 환불 처리 (첫 번째 차감 크레딧에 환불)
        if req.consumed_credit_ids:
            refunded = credit_service.refund(
                user_code,
                req.consumed_credit_ids[0],
                amount=1,
                reason=req.error_code or "chat_failed",
            )
        event_id = _publish_chat_failed_event(
            user_code=user_code,
            consume_id=req.consume_id,
            query=req.query,
            error_code=req.error_code or "unknown_error",
            session_id=req.session_id,
        )

    return LogChatResponse(event_id=event_id, refunded=refunded)


@router.post("/{user_code}/grant")
def grant_credits(
    user_code: str,
    req: GrantRequest,
    credit_service: Annotated[CreditService, Depends(get_credit_service)],
) -> CreditSummaryResponse:
    """관리자/이벤트 크레딧 부여."""
    expired_at = datetime.fromisoformat(req.expired_at)
    credit_service.grant(
        user_code=user_code,
        amount=req.amount,
        source=req.source,
        reason=req.reason,
        expired_at=expired_at,
    )

    # 새 잔액 반환
    summary = credit_service.get_summary(user_code)
    return CreditSummaryResponse(
        total_remaining=summary.total_remaining,
        credits=[
            CreditItemResponse(
                id=c.id,
                amount=c.amount,
                original_amount=c.original_amount,
                source=c.source,
                reason=c.reason,
                expired_at=c.expired_at.isoformat(),
            )
            for c in summary.credits
        ],
    )


@router.get("/{user_code}/history")
def get_credit_history(
    user_code: str,
    credit_service: Annotated[CreditService, Depends(get_credit_service)],
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse[CreditTransactionResponse]:
    """크레딧 사용 이력 조회."""
    items, total = credit_service.get_history(user_code, page, page_size)
    return PaginatedResponse(
        items=[
            CreditTransactionResponse(
                id=tx.id,
                type=tx.type,
                amount=tx.amount,
                reason=tx.reason,
                credit_id=tx.credit_id,
                created_at=tx.created_at.isoformat(),
            )
            for tx in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# -------- Event Publishing Helpers --------


def _publish_credit_consumed_event(
    user_code: str,
    consume_id: str,
    consumed_credit_ids: list[str],
    amount: int,
    remaining: int,
    reason: str,
) -> None:
    """credit.consumed 이벤트 발행."""
    now = datetime.now(timezone.utc).isoformat()
    event = CreditConsumedEvent(
        id=consume_id,
        type=CreditEventType.CREDIT_CONSUMED,
        timestamp=now,
        source="user-service",
        version="1.0",
        user_code=user_code,
        credit_expired_at="",  # 1:N 모델에서는 여러 크레딧일 수 있음
        amount=amount,
        remaining=remaining,
        reason=reason,
        session_id=None,
    )
    wrapped = new_json_event(payload=asdict(event), event_id=consume_id)
    bus = get_kafka_event_bus()
    bus.publish(TOPIC_CREDIT.base, wrapped)


def _publish_chat_completed_event(
    user_code: str,
    consume_id: str,
    query: str,
    answer: str,
    session_id: str | None = None,
) -> str:
    """chat.completed 이벤트 발행."""
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    event = ChatCompletedEvent(
        id=event_id,
        type=ChatEventType.CHAT_COMPLETED,
        timestamp=now,
        source="user-service",
        version="1.0",
        user_code=user_code,
        session_id=session_id,
        query=query,
        answer=answer,
        credit_consumed_id=consume_id,
        credit_expired_at="",
    )
    wrapped = new_json_event(payload=asdict(event), event_id=event_id)
    bus = get_kafka_event_bus()
    bus.publish(TOPIC_CHAT.base, wrapped)
    return event_id


def _publish_chat_failed_event(
    user_code: str,
    consume_id: str,
    query: str,
    error_code: str,
    session_id: str | None = None,
) -> str:
    """chat.failed 이벤트 발행."""
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    event = ChatFailedEvent(
        id=event_id,
        type=ChatEventType.CHAT_FAILED,
        timestamp=now,
        source="user-service",
        version="1.0",
        user_code=user_code,
        session_id=session_id,
        query=query,
        error_code=error_code,
        credit_consumed_id=consume_id,
        credit_expired_at="",
    )
    wrapped = new_json_event(payload=asdict(event), event_id=event_id)
    bus = get_kafka_event_bus()
    bus.publish(TOPIC_CHAT.base, wrapped)
    return event_id
