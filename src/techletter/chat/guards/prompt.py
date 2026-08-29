"""입력 가드.

**평가 지점은 한 곳이다.** 현행은 Go 게이트웨이와 Python 챗봇이 각각
평가해서 규칙이 어긋났고, 크레딧 차감 전후 순서도 달랐다(ISSUE-013).
여기서는 크레딧을 깎기 전에 한 번만 본다.
"""

from __future__ import annotations

import re

from techletter.chat.guards.models import GuardFinding, GuardResult
from techletter.chat.guards.rules import PROMPT_RULES

__all__ = ["POLICY_BLOCK_MESSAGE", "PromptGuard", "clip", "sanitize_untrusted"]

POLICY_BLOCK_MESSAGE = (
    "죄송합니다. 해당 요청은 보안 정책상 처리할 수 없습니다. "
    "Tech-Letter의 기술 콘텐츠와 관련된 질문으로 다시 요청해주세요."
)
SANITIZED_MESSAGE = "일부 지시성 문구를 제외하고 질문을 처리했습니다."

_WHITESPACE = re.compile(r"\s+")


ELLIPSIS = "..."


def clip(text: str, max_length: int) -> str:
    """`max_length`를 **넘지 않게** 자른다. 말줄임표 길이까지 계산에 넣는다.

    현행은 `text[: max_length - 1] + "..."`라 결과가 항상 2자 초과했다.
    프롬프트 예산을 세는 쪽에서 조용히 어긋난다.
    """
    if len(text) <= max_length:
        return text
    if max_length <= len(ELLIPSIS):
        return text[:max_length]
    return text[: max_length - len(ELLIPSIS)].rstrip() + ELLIPSIS


def sanitize_untrusted(text: str, *, max_length: int) -> str:
    """대화 기록처럼 신뢰할 수 없는 텍스트를 프롬프트에 넣기 전에 압축·절단한다."""
    return clip(_WHITESPACE.sub(" ", text).strip(), max_length)


class PromptGuard:
    def __init__(self) -> None:
        self._rules = PROMPT_RULES

    def inspect(self, text: str) -> GuardResult:
        normalized = text.strip()
        findings: list[GuardFinding] = []
        sanitized = normalized
        action = "pass"

        for rule in self._rules:
            if not rule.pattern.search(normalized):
                continue
            findings.append(GuardFinding(category=rule.category, severity="high"))
            if rule.action == "block":
                return GuardResult(
                    action="block",
                    risk_level="high",
                    text=normalized,
                    findings=findings,
                    message=POLICY_BLOCK_MESSAGE,
                )
            action = "sanitize"
            sanitized = rule.pattern.sub("", sanitized).strip()

        if action == "pass":
            return GuardResult(action="pass", risk_level="low", text=normalized)

        # 문구를 지웠더니 질문이 통째로 사라지면 원문을 쓴다. 빈 질문을
        # LLM에 보내는 것보다 낫다.
        return GuardResult(
            action="sanitize",
            risk_level="medium",
            text=sanitized or normalized,
            findings=findings,
            message=SANITIZED_MESSAGE,
        )
