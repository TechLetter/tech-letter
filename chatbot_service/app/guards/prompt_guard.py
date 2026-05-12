from __future__ import annotations

import re
from dataclasses import dataclass
from re import Pattern

from .schemas import GuardFinding, GuardResult


POLICY_BLOCK_MESSAGE = (
    "죄송합니다. 해당 요청은 보안 정책상 처리할 수 없습니다. "
    "Tech-Letter의 기술 콘텐츠와 관련된 질문으로 다시 요청해주세요."
)


@dataclass(frozen=True, slots=True)
class PromptGuardRule:
    category: str
    severity: str
    action: str
    pattern: Pattern[str]


class PromptGuard:
    def __init__(self) -> None:
        self._rules = [
            PromptGuardRule(
                category="system_prompt_extraction",
                severity="high",
                action="block",
                pattern=re.compile(
                    r"(?i)(((your|current|internal|hidden|exact|raw|full)\s+)(system|developer)\s+(prompt|message|instruction).*(show|print|reveal|dump|expose|display))"
                    r"|((show|print|reveal|dump|expose|display).*((your|current|internal|hidden|exact|raw|full)\s+)(system|developer)\s+(prompt|message|instruction))"
                    r"|((system|developer)\s+(prompt|message|instruction).*(verbatim|raw|exact|full|contents?).*(show|print|reveal|dump|expose|display))"
                    r"|(((너의|네|현재|내부|숨겨진|원문|전체|그대로)\s*)+(시스템|개발자)\s*(프롬프트|메시지|지시).*(보여|출력|공개|노출))"
                    r"|((보여|출력|공개|노출).*((너의|네|현재|내부|숨겨진|원문|전체|그대로)\s*)+(시스템|개발자)\s*(프롬프트|메시지|지시))"
                    r"|((시스템|개발자)\s*(프롬프트|메시지|지시).*(원문|전체|그대로|내용).*(보여|출력|공개|노출))"
                ),
            ),
            PromptGuardRule(
                category="role_override",
                severity="high",
                action="block",
                pattern=re.compile(
                    r"(?i)((ignore|forget|bypass|override).*(previous|prior|system|developer)\s+(instruction|prompt|message|rule))"
                    r"|((이전|기존)\s*(지시|규칙|명령).*(무시|잊어|우회|덮어))"
                    r"|(dan mode|jailbreak)"
                ),
            ),
            PromptGuardRule(
                category="secret_request",
                severity="high",
                action="block",
                pattern=re.compile(
                    r"(?i)((api[_ -]?key|secret|credential|env(?:ironment)? variable|access token).*(show|print|reveal|dump|expose|display))"
                    r"|((환경변수|비밀|시크릿|토큰|인증정보).*(보여|출력|공개|노출|알려))"
                ),
            ),
            PromptGuardRule(
                category="cross_user_data_request",
                severity="high",
                action="block",
                pattern=re.compile(
                    r"(?i)((other|another)\s+users?.*(chat|history|data|information).*(show|print|reveal|display))"
                    r"|((다른|타)\s*(사용자|유저).*(대화|기록|정보|데이터).*(보여|조회|알려))"
                ),
            ),
            PromptGuardRule(
                category="citation_bypass",
                severity="medium",
                action="sanitize",
                pattern=re.compile(r"(?i)(without sources|hide sources|출처\s*(없이|숨기고)|근거\s*(없이|숨기고))"),
            ),
        ]

    def inspect(self, text: str) -> GuardResult:
        normalized = text.strip()
        findings: list[GuardFinding] = []
        sanitized_text = normalized
        action = "allow"
        risk_level = "low"

        for rule in self._rules:
            if not rule.pattern.search(normalized):
                continue
            findings.append(
                GuardFinding(category=rule.category, severity=rule.severity)  # type: ignore[arg-type]
            )
            if rule.action == "block":
                return GuardResult(
                    action="block",
                    risk_level="high",
                    sanitized_text=normalized,
                    findings=findings,
                    message=POLICY_BLOCK_MESSAGE,
                )

            action = "sanitize"
            risk_level = "medium"
            sanitized_text = rule.pattern.sub("", sanitized_text).strip()

        if not sanitized_text:
            sanitized_text = normalized

        return GuardResult(
            action=action,  # type: ignore[arg-type]
            risk_level=risk_level,  # type: ignore[arg-type]
            sanitized_text=sanitized_text,
            findings=findings,
            message=(
                "일부 지시성 문구를 제외하고 질문을 처리했습니다."
                if action == "sanitize"
                else None
            ),
        )

    def sanitize_untrusted_text(self, text: str, *, max_length: int) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= max_length:
            return compact
        return compact[: max_length - 1].rstrip() + "..."
