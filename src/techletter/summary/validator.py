"""추출한 본문이 쓸 만한지 검사한다.

길이와 무관하게 본다. 대신 soft 마커(“not found” 같은 흔한 단어)만
짧은 문서로 제한한다 — 정상 기술 글에도 그 단어가 나오기 때문이다.
"""

from __future__ import annotations

from techletter.core.errors import PermanentError
from techletter.summary.constants import (
    BLOCK_MARKERS_SOFT,
    BLOCK_MARKERS_STRONG,
    BLOCK_MARKERS_UNKNOWN,
    MIN_TEXT_LENGTH,
)

__all__ = ["SOFT_MARKER_MAX_LENGTH", "validate_plain_text"]

# soft 마커는 이 길이 이하의 문서에서만 차단 근거로 쓴다.
SOFT_MARKER_MAX_LENGTH = 500


def validate_plain_text(text: str) -> None:
    """쓸 수 없는 본문이면 `PermanentError`. 재시도해도 같은 결과다."""
    stripped = (text or "").strip()
    if not stripped:
        raise PermanentError("extracted text is empty", reason="content_empty")
    if len(stripped) < MIN_TEXT_LENGTH:
        raise PermanentError(
            f"extracted text too short: {len(stripped)} < {MIN_TEXT_LENGTH}",
            reason="content_too_short",
        )

    lowered = stripped.lower()
    for marker in BLOCK_MARKERS_STRONG:
        if marker in lowered:
            raise PermanentError(f"bot challenge detected: {marker}", reason="bot_blocked")
    for marker in BLOCK_MARKERS_UNKNOWN:
        if marker in lowered:
            raise PermanentError(f"page not settled: {marker}", reason="unresolved_page")
    if len(lowered) <= SOFT_MARKER_MAX_LENGTH:
        for marker in BLOCK_MARKERS_SOFT:
            if marker in lowered:
                raise PermanentError(f"error page detected: {marker}", reason="error_page")
