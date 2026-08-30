"""요약 파이프라인이 쓰는 마커와 상수.

**모든 마커는 소문자다** — 비교 대상이 `html.lower()`라 대문자가 섞이면
영원히 매칭되지 않는다. 목록을 만들 때 소문자를 강제한다.
"""

from __future__ import annotations

__all__ = [
    "BLOCK_MARKERS_SOFT",
    "BLOCK_MARKERS_STRONG",
    "BLOCK_MARKERS_UNKNOWN",
    "CATEGORIES",
    "MIN_TEXT_LENGTH",
    "RETRY_MARKERS",
]


def _markers(*values: str) -> frozenset[str]:
    lowered = frozenset(value.lower() for value in values)
    # 대문자가 섞이면 조용히 죽는 규칙이 된다. 만들 때 확인한다.
    assert all(value == value.lower() for value in lowered)
    return lowered


# 확실한 봇/보안 차단.
BLOCK_MARKERS_STRONG = _markers(
    "verify you are human",
    "verifying you are human",
    "i'm not a robot",
    "bot check",
    "access denied",
    "security check",
    "cloudflare",
    "challenges.cloudflare.com",
    "enable javascript and cookies to continue",
    "apologies, but something went wrong on our end",
    "needs to review the security of your connection before proceeding",
)

# 로딩 중이거나 판단이 어려운 상태.
BLOCK_MARKERS_UNKNOWN = _markers(
    "just a moment",
    "redirecting",
    "loading...",
    "checking your browser",
    "refresh the page",
    "enable javascript",
)

# HTTP 오류 페이지. 본문에 흔한 단어라 짧은 문서에서만 본다.
BLOCK_MARKERS_SOFT = _markers(
    "not found",
    "forbidden",
    "internal server error",
    "bad request",
    "gateway timeout",
)

# 렌더러가 다시 시도할 근거. 차단 마커에 "잠시 후 다시" 계열을 더한다.
RETRY_MARKERS = (
    BLOCK_MARKERS_STRONG
    | BLOCK_MARKERS_UNKNOWN
    | _markers(
        "out of nothing, something.",
        "please wait while we verify",
    )
)

MIN_TEXT_LENGTH = 50

# 요약 카테고리 화이트리스트. 모델이 목록 밖의 값을 만들어 내면 버린다
# (실측에서 `lfm-2.5-2.6b`가 Frontend 글을 Infrastructure로 분류했다).
CATEGORIES = (
    "Backend",
    "Frontend",
    "Mobile",
    "AI",
    "Data Engineering",
    "DevOps",
    "Security",
    "Cloud",
    "Database",
    "Programming Languages",
    "Infrastructure",
    "Other",
)
