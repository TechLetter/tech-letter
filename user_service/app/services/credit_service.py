"""크레딧 서비스 (1:N 모델).

크레딧 집계 조회, FIFO 소비, 일일 지급, 환불, 트랜잭션 로깅을 처리한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..models.credit import CreditSummary, CreditTransaction
from ..repositories.interfaces import (
    CreditRepositoryInterface,
    CreditTransactionRepositoryInterface,
)


class CreditService:
    """크레딧 관련 비즈니스 로직 (1:N 모델)."""

    def __init__(
        self,
        credit_repo: CreditRepositoryInterface,
        transaction_repo: CreditTransactionRepositoryInterface,
    ) -> None:
        self._credit_repo = credit_repo
        self._transaction_repo = transaction_repo

    def get_summary(self, user_code: str) -> CreditSummary:
        """유저의 유효한 크레딧 합계 및 목록 조회."""
        return self._credit_repo.get_summary(user_code)

    def grant_daily(self, user_code: str) -> int:
        """일일 크레딧 지급. 지급된 양 반환 (이미 지급된 경우 0)."""
        credit = self._credit_repo.grant_daily(user_code)
        if credit is None:
            return 0

        # 트랜잭션 로그
        self._transaction_repo.create(
            CreditTransaction(
                user_code=user_code,
                credit_id=credit.id,
                type="grant",
                amount=credit.amount,
                reason="로그인 일일 지급",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        return credit.amount

    def consume(
        self, user_code: str, amount: int = 1, reason: str = "chat"
    ) -> tuple[list[str], int] | None:
        """크레딧 소비. 성공 시 (차감된 크레딧 ID 목록, 잔액) 반환, 실패 시 None."""
        result = self._credit_repo.consume(user_code, amount)
        if result is None:
            return None

        consumed_ids, remaining = result

        # 트랜잭션 로그
        self._transaction_repo.create(
            CreditTransaction(
                user_code=user_code,
                credit_id=consumed_ids[0] if consumed_ids else None,
                type="consume",
                amount=amount,
                reason=reason,
                metadata={"consumed_credit_ids": consumed_ids},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        return consumed_ids, remaining

    def refund(
        self, user_code: str, credit_id: str, amount: int = 1, reason: str = "refund"
    ) -> bool:
        """크레딧 환불. 성공 여부 반환."""
        credit = self._credit_repo.refund(credit_id, amount)
        if credit is None:
            return False

        # 트랜잭션 로그
        self._transaction_repo.create(
            CreditTransaction(
                user_code=user_code,
                credit_id=credit_id,
                type="refund",
                amount=amount,
                reason=reason,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        return True

    def grant(
        self,
        user_code: str,
        amount: int,
        source: str,
        reason: str,
        expired_at: datetime,
    ) -> int:
        """크레딧 부여 (관리자, 이벤트 등). 부여된 양 반환."""
        credit = self._credit_repo.grant(
            user_code=user_code,
            amount=amount,
            source=source,
            reason=reason,
            expired_at=expired_at,
        )

        # 트랜잭션 로그
        self._transaction_repo.create(
            CreditTransaction(
                user_code=user_code,
                credit_id=credit.id,
                type="admin_grant" if source == "admin" else "grant",
                amount=amount,
                reason=reason,
                metadata={"source": source},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        return amount

    def get_history(
        self, user_code: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[CreditTransaction], int]:
        """크레딧 사용 이력 조회."""
        return self._transaction_repo.list_by_user(user_code, page, page_size)
