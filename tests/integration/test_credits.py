"""크레딧 정합성 — 동시 요청에서도 잔액이 음수가 되면 안 되고, 중복 환불이
잔액을 부풀려도 안 된다.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from techletter.core.errors import InsufficientCreditsError
from techletter.core.time import utcnow
from techletter.users.credits import DAILY_CREDITS, CreditService, identity_hash
from techletter.users.repositories import (
    CreditRepository,
    CreditTransactionRepository,
    IdentityPolicyRepository,
)

pytestmark = pytest.mark.integration

USER = "google:test-user"


@pytest.fixture
def credit_service(mongo_db) -> CreditService:
    return CreditService(
        CreditRepository(mongo_db),
        CreditTransactionRepository(mongo_db),
        IdentityPolicyRepository(mongo_db),
    )


@pytest.fixture
def credits_repo(mongo_db) -> CreditRepository:
    return CreditRepository(mongo_db)


async def _give(repo: CreditRepository, amount: int, *, hours: int = 24, user: str = USER):
    return await repo.grant(
        user, amount, source="event", reason="테스트", expired_at=utcnow() + timedelta(hours=hours)
    )


async def test_grant_and_remaining(credit_service, credits_repo):
    await _give(credits_repo, 5)
    assert await credit_service.remaining(USER) == 5


async def test_expired_credits_are_excluded(credit_service, credits_repo):
    await credits_repo.grant(
        USER, 5, source="event", reason="만료됨", expired_at=utcnow() - timedelta(hours=1)
    )
    assert await credit_service.remaining(USER) == 0


async def test_consume_decrements(credit_service, credits_repo):
    await _give(credits_repo, 3)
    result = await credit_service.consume(USER)
    assert result.consumed == 1
    assert result.remaining == 2


async def test_consume_without_credits_raises(credit_service):
    with pytest.raises(InsufficientCreditsError):
        await credit_service.consume(USER)


async def test_concurrent_consume_never_goes_negative(credit_service, credits_repo):
    """잔액 3에 동시 요청 10건이면 정확히 3건만 성공해야 한다."""
    await _give(credits_repo, 3)

    results = await asyncio.gather(
        *(credit_service.consume(USER) for _ in range(10)), return_exceptions=True
    )
    succeeded = [r for r in results if not isinstance(r, BaseException)]
    failed = [r for r in results if isinstance(r, InsufficientCreditsError)]

    assert len(succeeded) == 3, "잔액보다 많이 차감되면 안 된다"
    assert len(failed) == 7
    assert await credit_service.remaining(USER) == 0


async def test_consume_uses_fifo_by_expiry(credit_service, credits_repo):
    """만료가 임박한 크레딧부터 쓴다."""
    soon = await _give(credits_repo, 1, hours=1)
    later = await _give(credits_repo, 1, hours=48)

    result = await credit_service.consume(USER)
    assert result.credit_ids == [soon.id]
    assert later.id not in result.credit_ids


async def test_consume_across_multiple_credits(credit_service, credits_repo):
    await _give(credits_repo, 1, hours=1)
    await _give(credits_repo, 1, hours=2)
    result = await credit_service.consume(USER, amount=2)
    assert result.consumed == 2
    assert len(result.credit_ids) == 2
    assert await credit_service.remaining(USER) == 0


async def test_partial_consume_is_rolled_back(credit_service, credits_repo):
    """2개가 필요한데 1개뿐이면 아무것도 차감하지 않아야 한다."""
    await _give(credits_repo, 1)
    with pytest.raises(InsufficientCreditsError):
        await credit_service.consume(USER, amount=2)
    assert await credit_service.remaining(USER) == 1, "실패 시 원복되어야 한다"


async def test_refund_restores(credit_service, credits_repo):
    await _give(credits_repo, 2)
    result = await credit_service.consume(USER)
    assert await credit_service.remaining(USER) == 1

    restored = await credit_service.refund(USER, result.credit_ids, "채팅 실패")
    assert restored == 1
    assert await credit_service.remaining(USER) == 2


async def test_refund_cannot_exceed_original_amount(credit_service, credits_repo):
    """중복 환불이 잔액을 부풀리면 안 된다."""
    await _give(credits_repo, 2)
    result = await credit_service.consume(USER)

    assert await credit_service.refund(USER, result.credit_ids, "1차") == 1
    assert await credit_service.refund(USER, result.credit_ids, "중복") == 0
    assert await credit_service.remaining(USER) == 2


async def test_grant_daily(credit_service):
    granted = await credit_service.grant_daily(USER, "google", "sub-1")
    assert granted == DAILY_CREDITS
    assert await credit_service.remaining(USER) == DAILY_CREDITS


async def test_grant_daily_uses_configured_amount(mongo_db):
    """DAILY_CREDIT_GRANT가 실제로 지급량을 바꿔야 한다 — 설정이 죽어있으면 안 된다."""
    service = CreditService(
        CreditRepository(mongo_db),
        CreditTransactionRepository(mongo_db),
        IdentityPolicyRepository(mongo_db),
        daily_credit_grant=3,
    )

    granted = await service.grant_daily(USER, "google", "sub-1")

    assert granted == 3
    assert await service.remaining(USER) == 3


async def test_grant_daily_is_idempotent_within_a_day(credit_service):
    assert await credit_service.grant_daily(USER, "google", "sub-1") == DAILY_CREDITS
    assert await credit_service.grant_daily(USER, "google", "sub-1") == 0
    assert await credit_service.remaining(USER) == DAILY_CREDITS


async def test_grant_daily_blocked_for_same_identity_new_account(credit_service):
    """계정을 다시 만들어도 같은 식별자면 오늘은 더 못 받는다."""
    assert await credit_service.grant_daily("google:first", "google", "sub-1") == DAILY_CREDITS
    assert await credit_service.grant_daily("google:second", "google", "sub-1") == 0


async def test_grant_daily_allows_different_identity(credit_service):
    assert await credit_service.grant_daily("google:a", "google", "sub-a") == DAILY_CREDITS
    assert await credit_service.grant_daily("google:b", "google", "sub-b") == DAILY_CREDITS


async def test_daily_credit_expires_next_midnight(credit_service, credits_repo):
    await credit_service.grant_daily(USER, "google", "sub-1")
    summary = await credits_repo.summary(USER)
    expiry = summary.credits[0].expired_at
    assert expiry.hour == 0
    assert expiry > utcnow()


async def test_admin_grant(credit_service):
    expires = utcnow() + timedelta(days=7)
    assert await credit_service.admin_grant(USER, 50, expires) == 50
    assert await credit_service.remaining(USER) == 50


async def test_transactions_are_logged(credit_service, credits_repo, mongo_db):
    await _give(credits_repo, 2)
    result = await credit_service.consume(USER)
    await credit_service.refund(USER, result.credit_ids, "환불")

    types = [doc["type"] async for doc in mongo_db["credit_transactions"].find({})]
    assert "consume" in types
    assert "refund" in types


async def test_identity_hash_is_stable():
    assert identity_hash("google", "sub-1") == identity_hash("google", "sub-1")
    assert identity_hash("google", "sub-1") != identity_hash("google", "sub-2")


async def test_remaining_bulk(credit_service, credits_repo):
    await _give(credits_repo, 3, user="google:a")
    await _give(credits_repo, 7, user="google:b")
    result = await credit_service.remaining_bulk(["google:a", "google:b", "google:none"])
    assert result == {"google:a": 3, "google:b": 7, "google:none": 0}
