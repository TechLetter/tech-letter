"""크레딧 도메인 모델 (1:N).

유저당 여러 크레딧 레코드를 가질 수 있으며, 각 레코드는 독립적인 만료시간을 가진다.
조회 시 유효한 크레딧의 합계를 반환하고, 소비 시 FIFO(만료 임박 순) 방식으로 차감한다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Credit(BaseModel):
    """개별 크레딧 레코드 도메인 모델."""

    id: str | None = None
    user_code: str
    amount: int  # 현재 남은 수량
    original_amount: int  # 최초 지급량
    source: str  # "daily" | "event" | "admin"
    reason: str  # 지급 사유
    expired_at: datetime
    created_at: datetime
    updated_at: datetime


class CreditSummary(BaseModel):
    """유저 크레딧 집계 결과."""

    user_code: str
    total_remaining: int  # 유효한 크레딧 합계
    credits: list[Credit]  # 개별 크레딧 목록 (expire 순)


class CreditTransaction(BaseModel):
    """크레딧 트랜잭션 로그 도메인 모델."""

    id: str | None = None
    user_code: str
    credit_id: str | None  # 연결된 크레딧 레코드 ID
    type: str  # "grant" | "consume" | "refund" | "admin_grant"
    amount: int
    reason: str
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime
