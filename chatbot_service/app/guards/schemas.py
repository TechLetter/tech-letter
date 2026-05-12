from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


GuardAction = Literal["allow", "sanitize", "block"]
RiskLevel = Literal["low", "medium", "high"]


@dataclass(slots=True)
class GuardFinding:
    category: str
    severity: RiskLevel


@dataclass(slots=True)
class GuardResult:
    action: GuardAction
    risk_level: RiskLevel
    sanitized_text: str
    findings: list[GuardFinding]
    message: str | None = None

    def to_metadata(self) -> dict:
        return {
            "action": self.action,
            "risk_level": self.risk_level,
            "message": self.message,
            "findings": [finding.category for finding in self.findings],
        }


class PolicyViolationError(Exception):
    def __init__(self, result: GuardResult) -> None:
        super().__init__(result.message or "policy_blocked")
        self.result = result


def dataclass_to_dict(value: object) -> dict:
    return asdict(value)
