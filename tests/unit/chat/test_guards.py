"""가드 — 검색 AI 요약의 출력 가드와 텍스트 자르기."""

from __future__ import annotations

import pytest

from techletter.chat.agent.prompts import BRIEF_ANSWER_SYSTEM_PROMPT
from techletter.chat.guards import BLOCKED_ANSWER, OutputGuard, clip
from techletter.chat.guards.rules import OUTPUT_LEAK_PHRASES


@pytest.mark.parametrize("phrase", OUTPUT_LEAK_PHRASES)
def test_output_leak_rules_are_bound_to_live_prompt_constants(phrase: str) -> None:
    """출력 가드는 검색 AI 요약에만 쓴다. 그 프롬프트의 문장과 맞춰 둔다."""
    assert phrase in BRIEF_ANSWER_SYSTEM_PROMPT
    assert OutputGuard().inspect(phrase).action == "block"


def test_a_normal_answer_passes_through_unchanged() -> None:
    result = OutputGuard().inspect("Kafka는 파티션 단위로 순서를 보장합니다.")

    assert result.action == "pass"
    assert result.text == "Kafka는 파티션 단위로 순서를 보장합니다."


def test_clipping_never_exceeds_the_limit() -> None:
    assert clip("가" * 50, 10) == "가" * 7 + "..."
    assert clip("짧다", 10) == "짧다"
    assert clip("가나다라", 2) == "가나"


def test_a_leaked_answer_is_replaced() -> None:
    result = OutputGuard().inspect(OUTPUT_LEAK_PHRASES[0])

    assert result.blocked
    assert result.text == BLOCKED_ANSWER
