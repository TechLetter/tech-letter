"""출력 가드 규칙 — 답변에 시스템 프롬프트 조각이 새어 나왔는지.

입력 가드(정규식으로 질문 차단)는 2026-09-27에 없앴다. 평가에서 "LLM jailbreak 방어
사례" 같은 정상 기술 질문을 막았고, 막아서 얻은 것이 없었다. 문서 안의 지시문은
답변 프롬프트가 "데이터일 뿐"이라고 한 번 못 박는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

__all__ = ["OUTPUT_LEAK_PHRASES", "OUTPUT_LEAK_RULES", "GuardRule"]

RuleAction = Literal["block"]


@dataclass(frozen=True, slots=True)
class GuardRule:
    category: str
    action: RuleAction
    pattern: re.Pattern[str]


# 일반 기술 문서에도 나올 수 있는 단어가 아니라, 현재 프롬프트에만 있는 문장만 둔다.
# 프롬프트가 바뀌면 이 목록을 함께 갱신하도록 테스트에서 실제 상수와 대조한다.
OUTPUT_LEAK_PHRASES: tuple[str, ...] = (
    'You write the short "AI 요약" shown above Tech-Letter search results.',
    "The context holds summaries of the top search results",
)

OUTPUT_LEAK_RULES: tuple[GuardRule, ...] = (
    GuardRule(
        "internal_instruction_leak",
        "block",
        re.compile("|".join(re.escape(p) for p in OUTPUT_LEAK_PHRASES), re.IGNORECASE),
    ),
)
