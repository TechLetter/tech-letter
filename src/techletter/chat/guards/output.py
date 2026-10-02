"""출력 가드 — 검색 AI 요약에 시스템 프롬프트 조각이 새어 나왔는지 본다."""

from __future__ import annotations

from techletter.chat.guards.models import GuardFinding, GuardResult
from techletter.chat.guards.rules import OUTPUT_LEAK_RULES

__all__ = ["BLOCKED_ANSWER", "OutputGuard"]

BLOCKED_ANSWER = "요약을 만들지 못했습니다."


class OutputGuard:
    def __init__(self) -> None:
        self._rules = OUTPUT_LEAK_RULES

    def inspect(self, answer: str) -> GuardResult:
        for rule in self._rules:
            if rule.pattern.search(answer):
                return GuardResult(
                    action="block",
                    risk_level="high",
                    text=BLOCKED_ANSWER,
                    findings=[GuardFinding(category=rule.category)],
                    message=BLOCKED_ANSWER,
                )
        return GuardResult(action="pass", risk_level="low", text=answer)
