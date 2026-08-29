"""출력 가드 — 답변에 시스템 프롬프트 조각이 새어 나왔는지 본다."""

from __future__ import annotations

from techletter.chat.guards.models import GuardFinding, GuardResult
from techletter.chat.guards.prompt import POLICY_BLOCK_MESSAGE
from techletter.chat.guards.rules import OUTPUT_LEAK_RULES

__all__ = ["OutputGuard"]


class OutputGuard:
    def __init__(self) -> None:
        self._rules = OUTPUT_LEAK_RULES

    def inspect(self, answer: str) -> GuardResult:
        for rule in self._rules:
            if rule.pattern.search(answer):
                return GuardResult(
                    action="block",
                    risk_level="high",
                    text=POLICY_BLOCK_MESSAGE,
                    findings=[GuardFinding(category=rule.category, severity="high")],
                    message=POLICY_BLOCK_MESSAGE,
                )
        return GuardResult(action="pass", risk_level="low", text=answer)
