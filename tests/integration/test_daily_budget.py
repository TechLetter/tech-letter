"""`DailyBudget` — 요약 한도 모델의 하루 장부."""

from __future__ import annotations

import pytest

from techletter.core.llm.budget import DailyBudget

pytestmark = pytest.mark.integration


async def test_consume_counts_up(mongo_db) -> None:
    budget = DailyBudget(mongo_db)

    await budget.consume("google")
    await budget.consume("google")

    assert await budget.used("google") == 2
    assert await budget.has_room("google", 3)
    assert not await budget.has_room("google", 2)


async def test_fill_spends_the_day(mongo_db) -> None:
    """구글이 일일 한도라고 답하면 장부를 한도까지 채운다."""
    budget = DailyBudget(mongo_db)
    await budget.consume("google")

    await budget.fill("google", 20)

    assert await budget.used("google") == 20
    assert not await budget.has_room("google", 20)


async def test_fill_never_lowers_the_count(mongo_db) -> None:
    budget = DailyBudget(mongo_db)
    await budget.consume("google", 25)

    await budget.fill("google", 20)

    assert await budget.used("google") == 25


async def test_fill_creates_the_day(mongo_db) -> None:
    budget = DailyBudget(mongo_db)

    await budget.fill("google:gemini-3.5-flash-lite", 450)

    assert await budget.used("google:gemini-3.5-flash-lite") == 450
