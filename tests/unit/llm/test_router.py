"""모델 라우터 — 무료 모델이 사라져도 서비스가 죽지 않아야 한다."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError, QuotaExceededError, RetryableError
from techletter.core.llm.errors import JsonOutputError
from techletter.core.llm.router import ModelRouter, truncate_for_model
from techletter.core.llm.scouter import ModelHealth
from techletter.core.llm.stats import ModelPurpose
from techletter.settings import RouterSettings

HEALTHY = [
    ModelHealth("nvidia/nemotron-3-super-120b-a12b:free", 100.0, 1168, 0, "OK"),
    ModelHealth("minimax/minimax-m3:free", 98.7, 3153, 0, "OK"),
    ModelHealth("inclusionai/ling-3.0-flash-fin:free", 100.0, 1549, 0, "OK"),
]


class FakeScouter:
    def __init__(self, models: list[ModelHealth] | None = None) -> None:
        self._models = models if models is not None else list(HEALTHY)
        self.calls = 0

    async def healthy_models(self) -> list[ModelHealth]:
        self.calls += 1
        return self._models


class FakeStats:
    def __init__(self, demoted: set[str] | None = None) -> None:
        self._demoted = demoted or set()
        self.records: list[tuple[str, bool]] = []

    async def demoted(self, purpose) -> set[str]:
        return self._demoted

    async def record(self, model_id, purpose, *, success, **kwargs) -> None:
        self.records.append((model_id, success))


def make_router(scouter=None, stats=None, **overrides) -> ModelRouter:
    settings = RouterSettings(
        SUMMARY_MODEL_PREFERENCE=overrides.pop(
            "summary_preference",
            "nvidia/nemotron-3-super-120b-a12b:free,minimax/minimax-m3:free",
        ),
        LLM_STATIC_FALLBACK_MODELS=overrides.pop("static_fallback", "minimax/minimax-m3:free"),
        **overrides,
    )
    return ModelRouter(settings, scouter or FakeScouter(), stats)


async def test_candidates_are_preference_intersect_healthy():
    router = make_router()
    candidates = await router.candidates(ModelPurpose.SUMMARY)
    assert candidates[0] == "nvidia/nemotron-3-super-120b-a12b:free"
    assert "inclusionai/ling-3.0-flash-fin:free" not in candidates, "선호목록에 없으면 제외"


async def test_candidates_skip_unhealthy_preference():
    """설정에 박힌 모델이 사라지는 것이 지금 겪는 장애다."""
    scouter = FakeScouter([HEALTHY[1]])  # nemotron이 목록에서 사라짐
    router = make_router(scouter)
    assert await router.candidates(ModelPurpose.SUMMARY) == ["minimax/minimax-m3:free"]


async def test_candidates_widen_when_preference_all_gone():
    """선호목록이 전부 죽으면 정상 목록 전체로 넓힌다."""
    scouter = FakeScouter([ModelHealth("some/other:free", 99.0, 900, 0, "OK")])
    router = make_router(scouter)
    assert await router.candidates(ModelPurpose.SUMMARY) == ["some/other:free"]


async def test_candidates_fall_back_to_static_when_scouter_empty():
    """scouter가 죽어도 서비스는 계속 동작해야 한다."""
    router = make_router(FakeScouter([]))
    assert await router.candidates(ModelPurpose.SUMMARY) == ["minimax/minimax-m3:free"]


async def test_candidates_are_capped():
    router = make_router(max_model_attempts=1)
    assert len(await router.candidates(ModelPurpose.SUMMARY)) == 1


async def test_demoted_models_are_pushed_back():
    stats = FakeStats(demoted={"nvidia/nemotron-3-super-120b-a12b:free"})
    router = make_router(stats=stats)
    candidates = await router.candidates(ModelPurpose.SUMMARY)
    assert candidates[0] == "minimax/minimax-m3:free"
    assert candidates[-1] == "nvidia/nemotron-3-super-120b-a12b:free"


async def test_run_returns_first_success():
    router = make_router()

    async def call(model_id: str) -> str:
        return f"answer from {model_id}"

    result, used = await router.run(ModelPurpose.SUMMARY, call)
    assert used == "nvidia/nemotron-3-super-120b-a12b:free"
    assert "answer from" in result


async def test_run_falls_back_on_rate_limit():
    tried: list[str] = []

    async def call(model_id: str) -> str:
        tried.append(model_id)
        if len(tried) == 1:
            raise RuntimeError("429 rate-limited upstream")
        return "ok"

    result, used = await make_router().run(ModelPurpose.SUMMARY, call)
    assert result == "ok"
    assert used == "minimax/minimax-m3:free"
    assert len(tried) == 2


async def test_run_falls_back_on_json_failure():
    """모델이 JSON 계약을 못 지키면 같은 모델을 재시도하지 않고 넘어간다."""
    tried: list[str] = []

    async def call(model_id: str) -> str:
        tried.append(model_id)
        if len(tried) == 1:
            raise JsonOutputError("summary 키가 없다")
        return "ok"

    result, _ = await make_router().run(ModelPurpose.SUMMARY, call)
    assert result == "ok"
    assert len(tried) == 2


async def test_run_propagates_permanent_error_immediately():
    """입력·프롬프트 문제는 모델을 바꿔도 같다."""
    tried: list[str] = []

    async def call(model_id: str) -> str:
        tried.append(model_id)
        raise PermanentError("context length exceeded")

    with pytest.raises(PermanentError):
        await make_router().run(ModelPurpose.SUMMARY, call)
    assert len(tried) == 1, "다음 모델로 넘어가면 안 된다"


async def test_run_raises_last_error_when_all_fail():
    async def call(model_id: str) -> str:
        raise RuntimeError("429 rate limit")

    with pytest.raises(RetryableError):
        await make_router().run(ModelPurpose.SUMMARY, call)


async def test_run_raises_quota_when_all_quota_exhausted():
    async def call(model_id: str) -> str:
        raise RuntimeError("RESOURCE_EXHAUSTED quota exceeded free_tier_requests limit: 20")

    with pytest.raises(QuotaExceededError):
        await make_router().run(ModelPurpose.SUMMARY, call)


async def test_run_without_any_candidate_is_retryable():
    router = make_router(FakeScouter([]), static_fallback="")

    async def call(model_id: str) -> str:  # pragma: no cover
        raise AssertionError

    with pytest.raises(RetryableError):
        await router.run(ModelPurpose.SUMMARY, call)


async def test_run_records_stats():
    stats = FakeStats()
    router = make_router(stats=stats)
    tried = 0

    async def call(model_id: str) -> str:
        nonlocal tried
        tried += 1
        if tried == 1:
            raise RuntimeError("429 rate limit")
        return "ok"

    await router.run(ModelPurpose.SUMMARY, call)
    assert stats.records[0][1] is False
    assert stats.records[1][1] is True


def test_truncate_for_model():
    assert truncate_for_model("abc", 10) == ("abc", False)
    assert truncate_for_model("abcdef", 3) == ("abc", True)
