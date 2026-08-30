"""users 도메인 문서 모델.

**필드명은 운영 컬렉션과 정확히 같아야 한다.** DTO에서만 이름을 바꾼다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from techletter.core.db.documents import BaseDocument, MongoDateTime

__all__ = [
    "Bookmark",
    "Credit",
    "CreditSource",
    "CreditSummary",
    "CreditTransaction",
    "IdentityPolicy",
    "LoginSession",
    "PolicyKey",
    "TransactionType",
    "User",
]

CreditSource = Literal["daily", "event", "admin"]
TransactionType = Literal["grant", "consume", "refund", "admin_grant"]


class User(BaseDocument):
    user_code: str
    """`<provider>:<uuid4>` 형태의 내부 식별자."""

    provider: str
    provider_sub: str
    email: str | None = None
    name: str | None = None
    profile_image: str | None = None
    role: str = "user"


class Credit(BaseDocument):
    """1:N 모델 — 유저당 여러 크레딧 문서가 있고 만료 임박 순으로 소비한다."""

    user_code: str
    amount: int
    original_amount: int
    source: CreditSource = "daily"
    reason: str = ""
    expired_at: MongoDateTime
    """TTL 인덱스 대상. 만료된 문서는 Mongo가 지운다."""


class CreditSummary(BaseDocument):
    """조회 결과 묶음. 저장되지 않는다."""

    user_code: str
    total_remaining: int = 0
    credits: list[Credit] = Field(default_factory=list)


class CreditTransaction(BaseDocument):
    user_code: str
    credit_id: str | None = None
    type: TransactionType
    amount: int
    reason: str = ""
    metadata: dict[str, Any] | None = None


class Bookmark(BaseDocument):
    user_code: str
    post_id: str
    """`posts._id`의 문자열 표현."""


class LoginSession(BaseDocument):
    """OAuth 콜백과 토큰 교환 사이의 1회용 세션(TTL 60초)."""

    session_id: str
    jwt_token: str
    expires_at: MongoDateTime


PolicyKey = Literal["DAILY_CREDIT_GRANT"]


class IdentityPolicy(BaseDocument):
    """식별자 기준 정책 사용 기록. 계정을 다시 만들어도 중복 지급을 막는다."""

    identity_hash: str
    policy_key: PolicyKey
    last_acted_at: MongoDateTime
