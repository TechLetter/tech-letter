"""한도 모델(Gemini 무료 등급) → 무료 모델 순서.

2026-09-27 요약 20건 중 4건이 무료 모델로 떨어졌다. 3 Flash가 503·429를 주자
라우터가 바로 무료 모델로 갔다. 2순위 3.5 Flash Lite는 후보에 없었다.
"""

from __future__ import annotations

import asyncio

import pytest

from techletter.core.errors import QuotaExceededError
from techletter.core.llm.chat import LlmGateway
from techletter.core.llm.quota import QuotaGate, QuotaModel, is_daily_quota_error
from techletter.core.llm.router import ModelRouter
from techletter.core.llm.scouter import ModelHealth
from techletter.settings import RouterSettings

FLASH = "gemini-3-flash-preview"
LITE = "gemini-3.5-flash-lite"
FREE = "inclusionai/ling-3.0-flash-fin:free"

UNAVAILABLE = "503 UNAVAILABLE. This model is currently experiencing high demand."
PER_MINUTE = (
    "429 RESOURCE_EXHAUSTED. You exceeded your current quota. "
    "quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
)
PER_DAY = (
    "429 RESOURCE_EXHAUSTED. You exceeded your current quota. "
    "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
)


class FakeScouter:
    async def healthy_models(self) -> list[ModelHealth]:
        return [ModelHealth(FREE, 100.0, 1000, 0, "OK")]


class FakeStats:
    def __init__(self) -> None:
        self.records: list[tuple[str, bool]] = []

    async def demoted(self, purpose) -> set[str]:
        return set()

    async def record(self, model_id, purpose, *, success) -> None:
        self.records.append((model_id, success))


class FakeBudget:
    def __init__(self, used: dict[str, int] | None = None) -> None:
        self.used = dict(used or {})

    async def has_room(self, provider: str, limit: int) -> bool:
        return limit <= 0 or self.used.get(provider, 0) < limit

    async def consume(self, provider: str, amount: int = 1) -> int:
        self.used[provider] = self.used.get(provider, 0) + amount
        return self.used[provider]

    async def fill(self, provider: str, limit: int) -> None:
        self.used[provider] = max(self.used.get(provider, 0), limit)


class ScriptedClient:
    """모델별로 정해 둔 예외를 던지고, 나머지는 JSON으로 답한다."""

    def __init__(self, failures: dict[str, str] | None = None) -> None:
        self.failures = failures or {}
        self.calls: list[str] = []

    async def complete(self, model_id, system, user, **kwargs) -> str:
        self.calls.append(model_id)
        if model_id in self.failures:
            raise RuntimeError(self.failures[model_id])
        return '{"ok": true}'


def build(client, budget, *, flash_rpm: int = 0, stats: FakeStats | None = None):
    gate = QuotaGate(
        budget,  # type: ignore[arg-type]
        [
            QuotaModel(FLASH, "google", 20, flash_rpm),
            QuotaModel(LITE, f"google:{LITE}", 450),
        ],
    )
    router = ModelRouter(RouterSettings(), FakeScouter(), stats)
    return LlmGateway(router, client, quota=gate)


async def test_quota_models_go_first_in_order() -> None:
    gateway = build(ScriptedClient(), FakeBudget())

    assert await gateway.candidates("summary") == [FLASH, LITE, FREE]


@pytest.mark.parametrize("failure", [UNAVAILABLE, PER_MINUTE])
async def test_a_failing_primary_falls_to_the_secondary_not_a_free_model(failure) -> None:
    """이게 고친 버그다."""
    client = ScriptedClient({FLASH: failure})
    budget = FakeBudget()

    _, model = await build(client, budget).complete_json("summary", "s", "u")

    assert model == LITE
    assert client.calls == [FLASH, LITE]
    # 실패한 호출도 구글 한도를 깎는다.
    assert budget.used == {"google": 1, f"google:{LITE}": 1}


async def test_a_spent_model_is_skipped_without_a_call_or_a_stat() -> None:
    client = ScriptedClient()
    stats = FakeStats()

    _, model = await build(client, FakeBudget({"google": 20}), stats=stats).complete_json(
        "summary", "s", "u"
    )

    assert model == LITE
    assert client.calls == [LITE]
    assert stats.records == [(LITE, True)]


async def test_both_spent_uses_free_models() -> None:
    client = ScriptedClient()
    budget = FakeBudget({"google": 20, f"google:{LITE}": 450})

    _, model = await build(client, budget).complete_json("summary", "s", "u")

    assert model == FREE
    assert client.calls == [FREE]


async def test_a_daily_quota_answer_fills_the_ledger() -> None:
    """구글이 일일 한도라고 하면 리셋 전까지 다시 부르지 않는다."""
    client = ScriptedClient({FLASH: PER_DAY})
    budget = FakeBudget({"google": 3})
    gateway = build(client, budget)

    await gateway.complete_json("summary", "s", "u")
    await gateway.complete_json("summary", "s", "u")

    assert budget.used["google"] == 20
    assert client.calls == [FLASH, LITE, LITE]


async def test_a_per_minute_answer_does_not_fill_the_ledger() -> None:
    budget = FakeBudget()

    await build(ScriptedClient({FLASH: PER_MINUTE}), budget).complete_json("summary", "s", "u")

    assert budget.used["google"] == 1


async def test_a_spent_model_does_not_wait_for_its_per_minute_limit() -> None:
    """예산을 다 쓴 모델 때문에 분당 한도를 기다리면 잡마다 1분씩 선다."""
    gateway = build(ScriptedClient(), FakeBudget({"google": 20}), flash_rpm=1)

    for _ in range(3):
        await asyncio.wait_for(gateway.complete_json("summary", "s", "u"), timeout=1)


async def test_everything_spent_waits_for_the_quota_reset() -> None:
    """후보가 전부 한도 모델이고 다 썼으면 잡은 리셋까지 기다린다."""
    gate = QuotaGate(FakeBudget({"google": 20}), [QuotaModel(FLASH, "google", 20)])  # type: ignore[arg-type]
    router = ModelRouter(RouterSettings(), FakeScouter())
    gateway = LlmGateway(router, ScriptedClient(), quota=gate)  # type: ignore[arg-type]

    with pytest.raises(QuotaExceededError):
        await gateway.complete_json("summary", "s", "u", candidates=[FLASH])


def test_only_daily_quota_messages_count_as_daily() -> None:
    assert is_daily_quota_error(RuntimeError(PER_DAY))
    assert not is_daily_quota_error(RuntimeError(PER_MINUTE))
    assert not is_daily_quota_error(RuntimeError(UNAVAILABLE))


def test_an_empty_model_id_is_not_a_quota_model() -> None:
    """`SUMMARY_SECONDARY_MODEL=""`로 2순위를 끈다."""
    models = [QuotaModel(FLASH, "google", 20), QuotaModel("", "google:", 450)]
    gate = QuotaGate(FakeBudget(), models)  # type: ignore[arg-type]

    assert gate.model_ids == [FLASH]
