from __future__ import annotations

import re

from .prompt_guard import POLICY_BLOCK_MESSAGE
from .schemas import GuardFinding, GuardResult


class OutputGuard:
    def __init__(self) -> None:
        self._leak_patterns = [
            re.compile(r"(?i)SYSTEM CONFIGURATION"),
            re.compile(r"(?i)CRITICAL SECURITY RULES"),
            re.compile(r"(?i)### FINAL REMINDER"),
            re.compile(r"(?i)### OPERATIONAL INSTRUCTIONS"),
        ]

    def inspect(self, answer: str) -> GuardResult:
        findings: list[GuardFinding] = []
        for pattern in self._leak_patterns:
            if pattern.search(answer):
                findings.append(
                    GuardFinding(category="internal_instruction_leak", severity="high")
                )
                return GuardResult(
                    action="block",
                    risk_level="high",
                    sanitized_text=POLICY_BLOCK_MESSAGE,
                    findings=findings,
                    message=POLICY_BLOCK_MESSAGE,
                )

        return GuardResult(
            action="allow",
            risk_level="low",
            sanitized_text=answer,
            findings=findings,
        )
