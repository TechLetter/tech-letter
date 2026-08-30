"""크레딧 서비스.

정책: 로그인 시 일일 크레딧 지급(기본 10, `DAILY_CREDIT_GRANT`), 채팅 1회당 1크레딧,
다음 UTC 자정에 소멸.
중복 지급은 식별자 해시 기준 정책으로 막는다(계정을 다시 만들어도 동일).

차감은 원자적이다 — 동시 요청에도 잔액이 음수가 되지 않는다. 환불에는
상한이 있어 중복 환불로 잔액이 부풀지 않는다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from techletter.core.errors import InsufficientCreditsError
from techletter.core.logging import get_logger
from techletter.core.time import utcnow
from techletter.users.models import CreditTransaction

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from bson import ObjectId

    from techletter.users.repositories import (
        CreditRepository,
        CreditTransactionRepository,
        IdentityPolicyRepository,
    )

__all__ = ["ConsumeResult", "CreditService", "identity_hash"]

logger = get_logger(__name__)

DAILY_CREDITS = 10
DAILY_POLICY_KEY = "DAILY_CREDIT_GRANT"


def identity_hash(provider: str, provider_sub: str) -> str:
    """계정을 다시 만들어도 같은 값이 나오는 식별자 해시."""
    return hashlib.sha256(f"{provider}:{provider_sub}".encode()).hexdigest()


@dataclass(slots=True)
class ConsumeResult:
    consumed: int
    remaining: int
    credit_ids: list[ObjectId] = field(default_factory=list)


class CreditService:
    def __init__(
        self,
        credits: CreditRepository,
        transactions: CreditTransactionRepository,
        policies: IdentityPolicyRepository,
        *,
        daily_credit_grant: int = DAILY_CREDITS,
    ) -> None:
        self._credits = credits
        self._transactions = transactions
        self._policies = policies
        self._daily_credit_grant = daily_credit_grant

    async def remaining(self, user_code: str) -> int:
        return await self._credits.remaining(user_code)

    async def remaining_bulk(self, user_codes: list[str]) -> dict[str, int]:
        """어드민 목록에서 유저별 잔액을 한 번에 조회한다(N+1 방지)."""
        return await self._credits.remaining_bulk(user_codes)

    async def consume(self, user_code: str, amount: int = 1) -> ConsumeResult:
        """크레딧을 차감한다. 부족하면 이미 뺀 만큼 되돌리고 402를 낸다.

        1씩 원자적으로 빼는 이유: 여러 크레딧 문서에 걸쳐 차감할 때 각 단계가
        조건부 단일 연산이어야 경쟁 상황에서 초과 차감이 생기지 않는다.
        실제 사용처는 채팅 1회 = 1크레딧이라 대개 한 번의 연산이다.
        """
        taken: list[ObjectId] = []
        for _ in range(amount):
            credit_id = await self._credits.take_one(user_code)
            if credit_id is None:
                for cid in taken:
                    await self._credits.give_back(cid, 1)
                raise InsufficientCreditsError
            taken.append(credit_id)

        remaining = await self._credits.remaining(user_code)
        await self._log(user_code, taken[0] if taken else None, "consume", -amount, "chat")
        return ConsumeResult(consumed=amount, remaining=remaining, credit_ids=taken)

    async def refund(self, user_code: str, credit_ids: list[ObjectId], reason: str) -> int:
        """차감을 되돌린다. 실제로 되돌린 개수를 준다."""
        restored = 0
        for credit_id in credit_ids:
            if await self._credits.give_back(credit_id, 1):
                restored += 1
        if restored:
            await self._log(user_code, credit_ids[0], "refund", restored, reason)
            logger.info("credits refunded", extra={"user_code": user_code, "restored": restored})
        return restored

    async def grant_daily(self, user_code: str, provider: str, provider_sub: str) -> int:
        """로그인 시 일일 지급. 이미 받았으면 0.

        식별자 정책과 유저 기준 검사를 모두 통과해야 지급한다.
        """
        allowed = await self._policies.try_use(
            identity_hash(provider, provider_sub), DAILY_POLICY_KEY
        )
        if not allowed:
            return 0
        if await self._credits.granted_today(user_code):
            return 0

        credit = await self._credits.grant(
            user_code,
            self._daily_credit_grant,
            source="daily",
            reason="로그인 일일 지급",
            expired_at=self._next_midnight(),
        )
        await self._log(user_code, credit.id, "grant", self._daily_credit_grant, "로그인 일일 지급")
        logger.info("daily credits granted", extra={"user_code": user_code})
        return self._daily_credit_grant

    async def admin_grant(
        self, user_code: str, amount: int, expires_at: datetime, reason: str = "어드민 수동 지급"
    ) -> int:
        credit = await self._credits.grant(
            user_code, amount, source="admin", reason=reason, expired_at=expires_at
        )
        await self._log(user_code, credit.id, "admin_grant", amount, reason)
        return amount

    async def delete_for_user(self, user_code: str) -> None:
        await self._credits.delete_by_user(user_code)
        await self._transactions.delete_by_user(user_code)

    @staticmethod
    def _next_midnight() -> datetime:
        """다음 UTC 자정."""
        today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return today + timedelta(days=1)

    async def _log(
        self,
        user_code: str,
        credit_id: ObjectId | None,
        tx_type: str,
        amount: int,
        reason: str,
    ) -> None:
        await self._transactions.create(
            CreditTransaction(
                user_code=user_code,
                credit_id=str(credit_id) if credit_id else None,
                type=tx_type,  # pyright: ignore[reportArgumentType]
                amount=amount,
                reason=reason,
            )
        )
