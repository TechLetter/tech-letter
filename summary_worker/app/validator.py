from __future__ import annotations

from .constants import (
    BLOCK_MARKERS_SOFT,
    BLOCK_MARKERS_STRONG,
    BLOCK_MARKERS_UNKNOWN,
)


class ContentValidationError(Exception):
    pass


def validate_plain_text(text: str) -> None:
    if not text or not text.strip():
        raise ContentValidationError("content_empty")

    text_lower = text.lower()

    if len(text_lower) < 50:
        raise ContentValidationError("content_too_short")

    if len(text_lower) < 500:
        for keyword in BLOCK_MARKERS_SOFT:
            if keyword in text_lower:
                raise ContentValidationError(f"soft_block:{keyword}")

    if len(text_lower) < 1000:
        for keyword in BLOCK_MARKERS_STRONG:
            if keyword in text_lower:
                raise ContentValidationError(f"strong_block:{keyword}")

        for keyword in BLOCK_MARKERS_UNKNOWN:
            if keyword in text_lower:
                raise ContentValidationError(f"unknown_content:{keyword}")
