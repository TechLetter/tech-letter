from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from common.models.identity_policy import PolicyKey
from user_service.app.models.credit import Credit, CreditSummary, CreditTransaction
from user_service.app.services.credit_service import CreditService


def _build_credit(
    *,
    credit_id: str,
    user_code: str = "user-001",
    amount: int = 10,
    source: str = "daily",
    reason: str = "로그인 일일 지급",
) -> Credit:
    now = datetime.now(timezone.utc)
    return Credit(
        id=credit_id,
        user_code=user_code,
        amount=amount,
        original_amount=amount,
        source=source,
        reason=reason,
        expired_at=now + timedelta(days=1),
        created_at=now,
        updated_at=now,
    )


class FakeCreditRepository:
    def __init__(self) -> None:
        self.grant_daily_result: Credit | None = None
        self.consume_result: tuple[list[str], int] | None = None
        self.refund_result: Credit | None = None
        self.grant_result: Credit = _build_credit(
            credit_id="credit-default",
            source="admin",
            reason="관리자 지급",
        )
        self.grant_daily_calls: list[str] = []
        self.consume_calls: list[tuple[str, int]] = []
        self.refund_calls: list[tuple[str, int]] = []
        self.grant_calls: list[tuple[str, int, str, str, datetime]] = []

    def get_summary(self, user_code: str) -> CreditSummary:
        return CreditSummary(user_code=user_code, total_remaining=0, credits=[])

    def get_summary_bulk(self, user_codes: list[str]) -> dict[str, int]:
        return {user_code: 0 for user_code in user_codes}

    def grant_daily(self, user_code: str) -> Credit | None:
        self.grant_daily_calls.append(user_code)
        return self.grant_daily_result

    def grant(
        self,
        user_code: str,
        amount: int,
        source: str,
        reason: str,
        expired_at: datetime,
    ) -> Credit:
        self.grant_calls.append((user_code, amount, source, reason, expired_at))
        return self.grant_result

    def consume(self, user_code: str, amount: int) -> tuple[list[str], int] | None:
        self.consume_calls.append((user_code, amount))
        return self.consume_result

    def refund(self, credit_id: str, amount: int) -> Credit | None:
        self.refund_calls.append((credit_id, amount))
        return self.refund_result

    def delete_by_user(self, user_code: str) -> bool:
        return True


class FakeCreditTransactionRepository:
    def __init__(self) -> None:
        self.created: list[CreditTransaction] = []

    def create(self, tx: CreditTransaction) -> CreditTransaction:
        self.created.append(tx)
        return tx

    def list_by_user(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list[CreditTransaction], int]:
        return [], 0


class FakeIdentityPolicyRepository:
    def __init__(self) -> None:
        self.allow = True
        self.calls: list[tuple[str, PolicyKey, int]] = []

    def try_use_policy(
        self,
        identity_hash: str,
        policy_key: PolicyKey,
        window_hours: int = 24,
    ) -> bool:
        self.calls.append((identity_hash, policy_key, window_hours))
        return self.allow


@dataclass
class CreditServiceFixture:
    service: CreditService
    credit_repo: FakeCreditRepository
    transaction_repo: FakeCreditTransactionRepository
    policy_repo: FakeIdentityPolicyRepository


def _build_fixture() -> CreditServiceFixture:
    credit_repo = FakeCreditRepository()
    transaction_repo = FakeCreditTransactionRepository()
    policy_repo = FakeIdentityPolicyRepository()
    service = CreditService(
        credit_repo=credit_repo,
        transaction_repo=transaction_repo,
        policy_repo=policy_repo,
    )
    return CreditServiceFixture(
        service=service,
        credit_repo=credit_repo,
        transaction_repo=transaction_repo,
        policy_repo=policy_repo,
    )


def test_grant_daily_returns_zero_when_policy_is_denied() -> None:
    fixture = _build_fixture()
    fixture.policy_repo.allow = False

    granted = fixture.service.grant_daily("user-001", "identity-001")

    assert granted == 0
    assert fixture.credit_repo.grant_daily_calls == []
    assert fixture.transaction_repo.created == []
    assert fixture.policy_repo.calls == [
        ("identity-001", PolicyKey.DAILY_CREDIT_GRANT, 24)
    ]


def test_grant_daily_logs_transaction_when_credit_is_granted() -> None:
    fixture = _build_fixture()
    fixture.credit_repo.grant_daily_result = _build_credit(
        credit_id="credit-daily-1",
        amount=10,
    )

    granted = fixture.service.grant_daily("user-001", "identity-001")

    assert granted == 10
    assert fixture.credit_repo.grant_daily_calls == ["user-001"]
    assert len(fixture.transaction_repo.created) == 1
    transaction = fixture.transaction_repo.created[0]
    assert transaction.user_code == "user-001"
    assert transaction.credit_id == "credit-daily-1"
    assert transaction.type == "grant"
    assert transaction.amount == 10
    assert transaction.reason == "로그인 일일 지급"


def test_consume_returns_none_when_balance_is_insufficient() -> None:
    fixture = _build_fixture()
    fixture.credit_repo.consume_result = None

    result = fixture.service.consume("user-001", amount=3, reason="chat-request")

    assert result is None
    assert fixture.credit_repo.consume_calls == [("user-001", 3)]
    assert fixture.transaction_repo.created == []


def test_consume_logs_transaction_when_successful() -> None:
    fixture = _build_fixture()
    fixture.credit_repo.consume_result = (["credit-1", "credit-2"], 7)

    result = fixture.service.consume("user-001", amount=3, reason="chat-request")

    assert result == (["credit-1", "credit-2"], 7)
    assert len(fixture.transaction_repo.created) == 1
    transaction = fixture.transaction_repo.created[0]
    assert transaction.type == "consume"
    assert transaction.credit_id == "credit-1"
    assert transaction.amount == 3
    assert transaction.reason == "chat-request"
    assert transaction.metadata == {"consumed_credit_ids": ["credit-1", "credit-2"]}


def test_refund_logs_transaction_when_successful() -> None:
    fixture = _build_fixture()
    fixture.credit_repo.refund_result = _build_credit(credit_id="credit-1", amount=5)

    refunded = fixture.service.refund(
        user_code="user-001",
        credit_id="credit-1",
        amount=2,
        reason="retry-failed-chat",
    )

    assert refunded is True
    assert fixture.credit_repo.refund_calls == [("credit-1", 2)]
    assert len(fixture.transaction_repo.created) == 1
    transaction = fixture.transaction_repo.created[0]
    assert transaction.type == "refund"
    assert transaction.credit_id == "credit-1"
    assert transaction.amount == 2
    assert transaction.reason == "retry-failed-chat"


def test_grant_uses_admin_grant_transaction_type_for_admin_source() -> None:
    fixture = _build_fixture()
    fixture.credit_repo.grant_result = _build_credit(
        credit_id="credit-admin-1",
        amount=20,
        source="admin",
        reason="관리자 수동 지급",
    )

    granted_credit = fixture.service.grant(
        user_code="user-001",
        amount=20,
        source="admin",
        reason="관리자 수동 지급",
        expired_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    assert granted_credit.id == "credit-admin-1"
    assert fixture.credit_repo.grant_calls
    assert len(fixture.transaction_repo.created) == 1
    transaction = fixture.transaction_repo.created[0]
    assert transaction.type == "admin_grant"
    assert transaction.amount == 20
    assert transaction.metadata == {"source": "admin"}
