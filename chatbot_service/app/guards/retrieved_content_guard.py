from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class RetrievedContentFinding:
    category: str
    severity: str


@dataclass(slots=True)
class RetrievedContentGuardResult:
    findings: list[RetrievedContentFinding]

    @property
    def risky(self) -> bool:
        return bool(self.findings)


class RetrievedContentGuard:
    def __init__(self) -> None:
        self._patterns = [
            (
                "embedded_instruction",
                re.compile(
                    r"(?i)(ignore previous instructions|developer message|system prompt|assistant instructions|이전 지시|시스템 프롬프트|개발자 메시지)"
                ),
            ),
            (
                "tool_hijacking",
                re.compile(r"(?i)(tool call|function call|execute this|run this|admin mode|관리자 모드|도구 호출)"),
            ),
            (
                "secret_request",
                re.compile(r"(?i)(api[_ -]?key|secret|credential|access token|환경변수|시크릿|인증정보)"),
            ),
        ]

    def inspect(self, text: str) -> RetrievedContentGuardResult:
        findings: list[RetrievedContentFinding] = []
        for category, pattern in self._patterns:
            if pattern.search(text):
                findings.append(
                    RetrievedContentFinding(category=category, severity="medium")
                )
        return RetrievedContentGuardResult(findings=findings)
