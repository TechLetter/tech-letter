"""summary_worker 전역에서 사용하는 공통 상수."""

from __future__ import annotations

# ── 봇/보안 차단 마커 ──────────────────────────────────────────────
# renderer (재시도 판단) 와 validator (검증) 양쪽에서 공유한다.

BLOCK_MARKERS_STRONG: frozenset[str] = frozenset({
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
})

BLOCK_MARKERS_UNKNOWN: frozenset[str] = frozenset({
    "just a moment",
    "redirecting",
    "loading...",
    "checking your browser",
    "refresh the page",
    "enable javascript",
})

BLOCK_MARKERS_SOFT: frozenset[str] = frozenset({
    "not found",
    "forbidden",
    "internal server error",
    "bad request",
    "gateway timeout",
})

# renderer 에서 재시도 판단에 사용하는 마커 (strong + unknown 합집합 + 기타)
RETRY_MARKERS: frozenset[str] = frozenset({
    "apologies, but something went wrong on our end.",
    "enable javascript and cookies to continue",
    "just a moment",
    "verifying you are human",
    "needs to review the security of your connection before proceeding",
    "Out of nothing, something.",
})

MIN_TEXT_LENGTH: int = 50
