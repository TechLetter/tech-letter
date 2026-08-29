"""요약 후처리 — 프롬프트로 지켜지지 않는 제약을 코드가 보장한다(ADR-0008)."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError
from techletter.settings import SummarySettings
from techletter.summary.constants import CATEGORIES
from techletter.summary.summarizer import (
    SYSTEM_INSTRUCTION,
    Summarizer,
    clip_to_sentence,
    normalize_categories,
    normalize_tags,
)


class FakeLlm:
    def __init__(self, payload: dict | Exception, model: str = "nvidia/nemotron:free") -> None:
        self.payload = payload
        self.model = model
        self.calls: list[dict] = []
        self.candidate_lists: list[list[str] | None] = []

    async def complete_json(self, purpose, system, user, **kwargs) -> tuple[dict, str]:
        self.calls.append({"purpose": purpose, "user": user})
        self.candidate_lists.append(kwargs.get("candidates"))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload, self.model

    async def candidates(self, purpose) -> list[str]:
        return ["free/a", "free/b"]


@pytest.fixture
def settings() -> SummarySettings:
    return SummarySettings()


def payload(**overrides) -> dict:
    return {
        "summary": "Kafka 리밸런싱의 원인과 대응을 정리한 글입니다.",
        "categories": ["Backend"],
        "tags": ["Kafka"],
        "error": None,
        **overrides,
    }


# ── 프롬프트 ────────────────────────────────────────────────────────
def test_the_prompt_declares_the_right_number_of_keys() -> None:
    """현행은 "five keys"라고 쓰고 4개만 정의해 환각을 유도했다(ISSUE-007 #4)."""
    assert "four keys" in SYSTEM_INSTRUCTION
    for key in ("summary", "categories", "tags", "error"):
        assert f'"{key}"' in SYSTEM_INSTRUCTION


def test_the_prompt_lists_the_category_whitelist() -> None:
    assert "Backend" in SYSTEM_INSTRUCTION
    assert "Programming Languages" in SYSTEM_INSTRUCTION


# ── 길이 후처리 ─────────────────────────────────────────────────────
def test_a_short_summary_is_left_alone() -> None:
    assert clip_to_sentence("짧은 요약입니다.", 200, 20) == "짧은 요약입니다."


def test_whitespace_is_collapsed() -> None:
    assert clip_to_sentence("여러   줄\n요약", 200, 20) == "여러 줄 요약"


def test_a_long_summary_is_cut_at_a_sentence_boundary() -> None:
    text = "첫 문장입니다. " * 40

    clipped = clip_to_sentence(text, 200, 20)

    assert len(clipped) <= 220
    assert clipped.endswith(".")


def test_a_summary_with_no_sentence_end_is_cut_with_an_ellipsis() -> None:
    clipped = clip_to_sentence("가" * 500, 200, 20)

    assert len(clipped) <= 221
    assert clipped.endswith("…")


def test_english_sentence_ends_are_recognized() -> None:
    clipped = clip_to_sentence("This is a sentence. " * 30, 200, 20)

    assert clipped.endswith(".")


# ── 카테고리·태그 후처리 ────────────────────────────────────────────
def test_categories_outside_the_whitelist_are_dropped() -> None:
    """`lfm-2.5-2.6b`가 Frontend 글을 Infrastructure로 분류한 실측이 있다."""
    assert normalize_categories(["Backend", "우주공학", "Frontend"]) == ["Backend", "Frontend"]


def test_category_matching_ignores_case() -> None:
    assert normalize_categories(["backend", "  AI  "]) == ["Backend", "AI"]


def test_categories_fall_back_to_other() -> None:
    assert normalize_categories([]) == ["Other"]
    assert normalize_categories("nope") == ["Other"]
    assert normalize_categories(["존재하지 않음"]) == ["Other"]


def test_categories_are_capped_at_three() -> None:
    assert len(normalize_categories(list(CATEGORIES))) == 3


def test_tags_are_deduped_case_insensitively() -> None:
    assert normalize_tags(["Kafka", "kafka", "Redis"], 7) == ["Kafka", "Redis"]


def test_tags_are_capped() -> None:
    assert len(normalize_tags([f"tag{i}" for i in range(20)], 7)) == 7


def test_absurdly_long_tags_are_dropped() -> None:
    assert normalize_tags(["Kafka", "x" * 100], 7) == ["Kafka"]


def test_non_list_tags_are_ignored() -> None:
    assert normalize_tags("Kafka", 7) == []


# ── 요약 호출 ───────────────────────────────────────────────────────
async def test_a_normal_summary_is_returned(settings) -> None:
    llm = FakeLlm(payload())

    result = await Summarizer(llm, settings).summarize("본문")  # type: ignore[arg-type]

    assert result.summary.startswith("Kafka")
    assert result.categories == ["Backend"]
    assert result.model_name == "nvidia/nemotron:free"
    assert result.truncated_input is False


async def test_an_error_field_is_a_permanent_failure(settings) -> None:
    llm = FakeLlm(payload(error="봇 차단 페이지입니다", summary=""))

    with pytest.raises(PermanentError) as excinfo:
        await Summarizer(llm, settings).summarize("본문")  # type: ignore[arg-type]

    assert excinfo.value.reason == "not_summarizable"


async def test_an_empty_summary_is_rejected_even_without_an_error(settings) -> None:
    """현행은 `error`만 보고 빈 요약을 통과시켰다(ISSUE-007 #3)."""
    llm = FakeLlm(payload(summary="   "))

    with pytest.raises(PermanentError) as excinfo:
        await Summarizer(llm, settings).summarize("본문")  # type: ignore[arg-type]

    assert excinfo.value.reason == "empty_summary"


async def test_a_huge_body_is_truncated(settings) -> None:
    settings.max_input_chars = 100
    llm = FakeLlm(payload())

    result = await Summarizer(llm, settings).summarize("가" * 5000)  # type: ignore[arg-type]

    assert result.truncated_input is True
    assert len(llm.calls[0]["user"]) == 100


# ── 예산 (D13) ──────────────────────────────────────────────────────
class FakeBudget:
    def __init__(self, has_room: bool = True) -> None:
        self._has_room = has_room
        self.consumed: list[str] = []

    async def has_room(self, provider: str, limit: int) -> bool:
        return self._has_room

    async def consume(self, provider: str, amount: int = 1) -> int:
        self.consumed.append(provider)
        return len(self.consumed)


async def test_the_primary_model_goes_first_while_budget_remains(settings) -> None:
    llm = FakeLlm(payload(), model="gemini-3-flash-preview")
    budget = FakeBudget(has_room=True)

    await Summarizer(
        llm,  # type: ignore[arg-type]
        settings,
        budget=budget,  # type: ignore[arg-type]
        primary_model="gemini-3-flash-preview",
        daily_limit=20,
    ).summarize("본문")

    assert llm.candidate_lists[0] == ["gemini-3-flash-preview", "free/a", "free/b"]
    assert budget.consumed == ["google"]


async def test_an_exhausted_budget_falls_back_to_the_router(settings) -> None:
    """예산을 넘기면 429를 맞고 재시도하는 대신 미리 무료 모델로 간다."""
    llm = FakeLlm(payload())
    budget = FakeBudget(has_room=False)

    await Summarizer(
        llm,  # type: ignore[arg-type]
        settings,
        budget=budget,  # type: ignore[arg-type]
        primary_model="gemini-3-flash-preview",
        daily_limit=20,
    ).summarize("본문")

    assert llm.candidate_lists[0] is None
    assert budget.consumed == []


async def test_budget_is_not_consumed_when_a_fallback_model_answers(settings) -> None:
    llm = FakeLlm(payload(), model="free/a")
    budget = FakeBudget(has_room=True)

    await Summarizer(
        llm,  # type: ignore[arg-type]
        settings,
        budget=budget,  # type: ignore[arg-type]
        primary_model="gemini-3-flash-preview",
        daily_limit=20,
    ).summarize("본문")

    assert budget.consumed == []


async def test_without_a_budget_the_router_decides(settings) -> None:
    llm = FakeLlm(payload())

    await Summarizer(llm, settings).summarize("본문")  # type: ignore[arg-type]

    assert llm.candidate_lists[0] is None
