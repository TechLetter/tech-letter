from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class GrantCreditRequest(BaseModel):
    """어드민 수동 크레딧 지급 요청."""

    amount: int
    expires_at: datetime


class GrantCreditResponse(BaseModel):
    """크레딧 지급 결과."""

    user_code: str
    amount: int
    expires_at: datetime
