"""요약 파이프라인이 쓰는 마커와 상수.

**모든 마커는 소문자다** — 비교 대상이 `html.lower()`라 대문자가 섞이면
영원히 매칭되지 않는다. 목록을 만들 때 소문자를 강제한다.
"""

from __future__ import annotations

__all__ = [
    "BLOCK_MARKERS_SOFT",
    "BLOCK_MARKERS_STRONG",
    "BLOCK_MARKERS_UNKNOWN",
    "MIN_TEXT_LENGTH",
    "RETRY_MARKERS",
]


def _markers(*values: str) -> frozenset[str]:
    lowered = frozenset(value.lower() for value in values)
    # 대문자가 섞이면 조용히 죽는 규칙이 된다. 만들 때 확인한다.
    assert all(value == value.lower() for value in lowered)
    return lowered


# 확실한 봇/보안 차단. 정상 기술 글에 나올 법한 흔한 단어는 넣지 않는다 —
# 길이와 무관하게 막으므로 Cloudflare 블로그 글이 "cloudflare" 한 단어로 전부
# dead가 된 적이 있다. 그런 단어는 아래 SOFT로 보낸다.
BLOCK_MARKERS_STRONG = _markers(
    "verify you are human",
    "verifying you are human",
    "i'm not a robot",
    "bot check",
    "challenges.cloudflare.com",
    "attention required! | cloudflare",
    "sorry, you have been blocked",
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

# HTTP 오류·차단 페이지. 본문에 흔한 단어라 짧은 문서에서만 본다.
BLOCK_MARKERS_SOFT = _markers(
    "not found",
    "forbidden",
    "internal server error",
    "bad request",
    "gateway timeout",
    "access denied",
    "security check",
    "cloudflare",
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
