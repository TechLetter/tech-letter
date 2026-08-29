"""가드 결과 타입.

`action`은 04 §3.6의 DTO 값(`pass`/`sanitize`/`block`)을 그대로 쓴다.
현행 내부 값은 `allow`였는데, 도메인과 계약에서 이름이 다를 이유가 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = ["GuardAction", "GuardFinding", "GuardResult", "RiskLevel"]

GuardAction = Literal["pass", "sanitize", "block"]
RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class GuardFinding:
    category: str
    severity: RiskLevel


@dataclass(frozen=True, slots=True)
class GuardResult:
    action: GuardAction
    risk_level: RiskLevel
    text: str
    findings: list[GuardFinding] = field(default_factory=list)
    message: str | None = None

    @property
    def blocked(self) -> bool:
        return self.action == "block"

    def to_metadata(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "risk_level": self.risk_level,
            "message": self.message,
            "findings": [finding.category for finding in self.findings],
        }
