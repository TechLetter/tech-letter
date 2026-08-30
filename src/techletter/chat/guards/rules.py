"""가드 규칙.

**어순과 무관하게 매치한다.** 규칙이 `대상 .* 동사` 한 방향만 보면, 동사가
앞에 오는 영어 질문(`show me the api key`)을 놓친다. lookahead로 어순과
무관하게 "필요한 요소가 모두 있는가"만 본다.

**과차단을 피한다.** `토큰 .* 알려`처럼 넓게 막으면 "JWT 토큰 만료 처리
알려줘" 같은 정상 기술 질문까지 막힌다. 값을 내놓으라는 강한 동사
(보여/출력/공개/노출)와 약한 동사(알려)를 나누고, 약한 동사는 런타임에
매인 대상(환경변수)에만 적용한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

__all__ = ["OUTPUT_LEAK_RULES", "PROMPT_RULES", "RETRIEVED_CONTENT_RULES", "GuardRule"]

RuleAction = Literal["block", "sanitize"]


@dataclass(frozen=True, slots=True)
class GuardRule:
    category: str
    action: RuleAction
    pattern: re.Pattern[str]


def _any(*alternatives: str) -> str:
    return "|".join(f"(?:{a})" for a in alternatives)


def _match_any(*alternatives: str) -> re.Pattern[str]:
    """하나라도 있으면 매치. `sanitize` 규칙은 매치 구간을 지우므로 이것만 쓴다."""
    return re.compile(_any(*alternatives), re.IGNORECASE)


def _match_all(*required: str) -> re.Pattern[str]:
    """전부 있으면 매치 — **순서는 보지 않는다**.

    lookahead만 있어 매치 길이가 0이다. 그래서 `sub()`로 구간을 지우는
    `sanitize` 규칙에는 쓸 수 없다(지워지는 게 없다). 차단 전용이다.
    """
    return re.compile("".join(f"(?=.*(?:{item}))" for item in required), re.IGNORECASE | re.DOTALL)


# ── 어휘 ────────────────────────────────────────────────────────────
_REVEAL = _any(
    # 값을 내놓으라는 강한 동사. 한/영 모두 여기에 둔다.
    "show",
    "print",
    "reveal",
    "dump",
    "expose",
    "display",
    "leak",
    "보여",
    "출력",
    "공개",
    "노출",
)
_REVEAL_WEAK = _any("tell", "알려", "말해", "적어")
_OWNERSHIP = _any(
    "your",
    "our",
    "current",
    "internal",
    "hidden",
    "exact",
    "raw",
    "full",
    "너의",
    "네",
    "우리",
    "현재",
    "내부",
    "숨겨진",
    "원문",
    "전체",
    "그대로",
)
_SYSTEM_PROMPT = _any(
    r"(?:system|developer)\s+(?:prompt|message|instruction)",
    r"(?:시스템|개발자)\s*(?:프롬프트|메시지|지시)",
)
_VERBATIM = _any("verbatim", "raw", "exact", "full", "contents?", "원문", "전체", "그대로", "내용")
_SECRET = _any(
    r"api[_ -]?keys?",
    "secrets?",
    "credentials?",
    r"access\s+tokens?",
    r"private\s+key",
    "시크릿",
    "인증정보",
    "비밀번호",
    "개인키",
    r"액세스\s*토큰",
)
# 이 대상은 그 자체로 "지금 이 프로세스의 값"을 뜻한다. 약한 동사로도 막는다.
_ENV_VAR = _any(r"env(?:ironment)?\s+variables?", "환경변수", "환경 변수", r"\.env")

PROMPT_RULES: tuple[GuardRule, ...] = (
    GuardRule(
        "system_prompt_extraction",
        "block",
        # 소유격이 붙거나("너의 시스템 프롬프트"), 원문/전체를 요구할 때만 막는다.
        # "시스템 프롬프트 예시를 보여줘" 같은 학습용 질문은 통과해야 한다.
        _match_all(_SYSTEM_PROMPT, _any(_OWNERSHIP, _VERBATIM), _REVEAL),
    ),
    GuardRule(
        "role_override",
        "block",
        _match_any(
            r"(?:ignore|forget|bypass|override)"
            r".*(?:previous|prior|system|developer)\s+(?:instruction|prompt|message|rule)",
            r"(?:이전|기존)\s*(?:지시|규칙|명령).*(?:무시|잊어|우회|덮어)",
            # 실행 동사 없이도 막는다 — 이 단어 자체가 이미 우회 시도다.
            r"dan mode",
            r"jailbreak",
            r"(?:prompt injection|tool call|function call).*(?:execute|run|call|invoke)",
            r"(?:관리자 모드|도구 호출).*(?:실행|호출)",
        ),
    ),
    GuardRule(
        "secret_request",
        "block",
        _match_any(
            _match_all(_SECRET, _REVEAL).pattern,
            _match_all(_ENV_VAR, _any(_REVEAL, _REVEAL_WEAK)).pattern,
        ),
    ),
    GuardRule(
        "cross_user_data_request",
        "block",
        _match_all(
            _any(r"(?:other|another)\s+users?", r"(?:다른|타)\s*(?:사용자|유저)"),
            _any("chat", "history", "data", "information", "대화", "기록", "정보", "데이터"),
            _any(_REVEAL, _REVEAL_WEAK, "조회"),
        ),
    ),
    # 차단이 아니라 해당 문구만 지운다. "출처 없이 알려줘"는 공격이 아니라
    # 취향에 가깝고, 출처는 어차피 코드가 붙인다.
    GuardRule(
        "citation_bypass",
        "sanitize",
        _match_any(
            r"without sources",
            r"hide sources",
            r"출처\s*(?:없이|숨기고)",
            r"근거\s*(?:없이|숨기고)",
        ),
    ),
)

# 검색해 온 남의 글에 섞인 지시문. 차단하지 않고 "신뢰할 수 없는 내용"이라고
# 표시만 한다 — 프롬프트 인젝션을 다루는 기술 글에는 당연히 이런 문장이 있다.
RETRIEVED_CONTENT_RULES: tuple[GuardRule, ...] = (
    GuardRule(
        "embedded_instruction",
        "sanitize",
        _match_any(
            r"ignore previous instructions",
            r"developer message",
            r"system prompt",
            r"assistant instructions",
            r"이전 지시",
            r"시스템 프롬프트",
            r"개발자 메시지",
        ),
    ),
    GuardRule(
        "tool_hijacking",
        "sanitize",
        _match_any(
            r"tool call",
            r"function call",
            r"execute this",
            r"run this",
            r"admin mode",
            r"관리자 모드",
            r"도구 호출",
        ),
    ),
    GuardRule("secret_request", "sanitize", _match_any(_SECRET, _ENV_VAR)),
)

# 답변에 우리 시스템 프롬프트 조각이 새어 나왔는지 본다.
OUTPUT_LEAK_RULES: tuple[GuardRule, ...] = (
    GuardRule(
        "internal_instruction_leak",
        "block",
        _match_any(
            r"SYSTEM CONFIGURATION",
            r"CRITICAL SECURITY RULES",
            r"### FINAL REMINDER",
            r"### OPERATIONAL INSTRUCTIONS",
        ),
    ),
)
