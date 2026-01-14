"""크레딧 서비스 (1:N 모델).

크레딧 집계 조회, FIFO 소비, 일일 지급, 환불, 트랜잭션 로깅을 처리한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends
from pymongo.database import Database

from common.mongo.client import get_database

from ..models.credit import (
    Credit,
    CreditSummary,
    CreditTransaction,
)
from ..repositories.credit_repository import CreditRepository
from ..repositories.interfaces import (
    CreditRepositoryInterface,
    CreditTransactionRepositoryInterface,
    IdentityPolicyRepositoryInterface,
)
from common.models.identity_policy import PolicyKey


def get_credit_repository(
    db: Database = Depends(get_database),
) -> CreditRepositoryInterface:
    """FastAPI DI용 CreditRepository 팩토리."""
    return CreditRepository(db)


def get_credit_transaction_repository(
    db: Database = Depends(get_database),
) -> CreditTransactionRepositoryInterface:
    """FastAPI DI용 CreditTransactionRepository 팩토리."""
    from ..repositories.credit_repository import CreditTransactionRepository

    return CreditTransactionRepository(db)


def get_identity_policy_repository(
    db: Database = Depends(get_database),
) -> IdentityPolicyRepositoryInterface:
    """FastAPI DI용 IdentityPolicyRepository 팩토리."""
    from ..repositories.identity_policy_repository import IdentityPolicyRepository

    return IdentityPolicyRepository(db)


def get_credit_service(
    credit_repo: CreditRepositoryInterface = Depends(get_credit_repository),
    transaction_repo: CreditTransactionRepositoryInterface = Depends(
        get_credit_transaction_repository
    ),
    policy_repo: IdentityPolicyRepositoryInterface = Depends(
        get_identity_policy_repository
    ),
) -> CreditService:
    """FastAPI DI용 CreditService 팩토리."""
    return CreditService(
        credit_repo=credit_repo,
        transaction_repo=transaction_repo,
        policy_repo=policy_repo,
    )


class CreditService:
    """크레딧 관련 비즈니스 로직 (1:N 모델)."""

    def __init__(
        self,
        credit_repo: CreditRepositoryInterface,
        transaction_repo: CreditTransactionRepositoryInterface,
        policy_repo: IdentityPolicyRepositoryInterface,
    ) -> None:
        self._credit_repo = credit_repo
        self._transaction_repo = transaction_repo
        self._policy_repo = policy_repo

    def _log_transaction(
        self,
        user_code: str,
        credit_id: str | None,
        tx_type: str,
        amount: int,
        reason: str,
        metadata: dict | None = None,
    ) -> None:
        """트랜잭션 로그를 기록한다."""
        self._transaction_repo.create(
            CreditTransaction(
                user_code=user_code,
                credit_id=credit_id,
                type=tx_type,
                amount=amount,
                reason=reason,
                metadata=metadata,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    def get_summary(self, user_code: str) -> CreditSummary:
        """유저의 유효한 크레딧 합계 및 목록 조회."""
        return self._credit_repo.get_summary(user_code)

    def grant_daily(self, user_code: str, identity_hash: str) -> int:
        """일일 크레딧 지급. 지급된 양 반환 (이미 지급된 경우 0).

        Identity Policy를 통해 중복 지급을 체크한다.
        """
        # 1. 정책 체크 (Atomic)
        allowed = self._policy_repo.try_use_policy(
            identity_hash=identity_hash,
            policy_key=PolicyKey.DAILY_CREDIT_GRANT,
        )
        if not allowed:
            return 0

        # 2. 실제 지급 (기존 로직 유지하되 중복 체크는 위에서 했으므로 바로 지급)
        # 단, CreditRepository.grant_daily 내부에도 로직이 있는데,
        # CreditRepository.grant_daily는 'user_code' 기준 체크임.
        # 이제 Identity 기준 체크를 통과했으므로, User 기준 체크는 굳이 안 해도 되지만
        # 방어적으로 남겨두거나, 일반 grant를 써도 됨.
        # 기존 grant_daily를 호출하면 user_code 기준으로 또 체크함. (나쁘지 않음)

        credit = self._credit_repo.grant_daily(user_code)
        if credit is None:
            # Identity는 통과했는데 User 기준 중복? (그럴 일 거의 없지만)
            # 이 경우 Policy는 사용처리 되었는데 크레딧 못 받음 -> 손해?
            # 하지만 Identity 체크가 더 상위 개념이므로 '오늘 이미 받음'으로 간주.
            return 0

        self._log_transaction(
            user_code=user_code,
            credit_id=credit.id,
            tx_type="grant",
            amount=credit.amount,
            reason="로그인 일일 지급",
        )
        return credit.amount

    def consume(
        self, user_code: str, amount: int = 1, reason: str = "consume"
    ) -> tuple[list[str], int] | None:
        """FIFO 방식으로 크레딧 차감. 성공 시 (차감된 ID 목록, 잔액) 반환."""
        result = self._credit_repo.consume(user_code, amount)
        if result is None:
            return None

        consumed_ids, remaining = result

        self._log_transaction(
            user_code=user_code,
            credit_id=consumed_ids[0] if consumed_ids else "",
            tx_type="consume",
            amount=amount,
            reason=reason,
            metadata={"consumed_credit_ids": consumed_ids},
        )
        return consumed_ids, remaining

    def refund(self, user_code: str, credit_id: str, amount: int, reason: str) -> bool:
        """크레딧 환불. 특정 credit에 amount만큼 복구."""
        credit = self._credit_repo.refund(credit_id, amount)
        if not credit:
            return False

        self._log_transaction(
            user_code=user_code,
            credit_id=credit_id,
            tx_type="refund",
            amount=amount,
            reason=reason,
        )
        return True

    def grant(
        self,
        user_code: str,
        amount: int,
        source: str,
        reason: str,
        expired_at: datetime,
    ) -> Credit:
        """크레딧 부여 (관리자, 이벤트 등). Credit 객체 반환."""
        credit = self._credit_repo.grant(
            user_code=user_code,
            amount=amount,
            source=source,
            reason=reason,
            expired_at=expired_at,
        )

        self._log_transaction(
            user_code=user_code,
            credit_id=credit.id,
            tx_type="admin_grant" if source == "admin" else "grant",
            amount=amount,
            reason=reason,
            metadata={"source": source},
        )
        return credit

    def get_history(
        self, user_code: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[CreditTransaction], int]:
        """크레딧 사용 이력 조회."""
        return self._transaction_repo.list_by_user(user_code, page, page_size)
