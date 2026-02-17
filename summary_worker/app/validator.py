from __future__ import annotations

from .constants import (
    BLOCK_MARKERS_SOFT,
    BLOCK_MARKERS_STRONG,
    BLOCK_MARKERS_UNKNOWN,
    MIN_TEXT_LENGTH,
)
from .exceptions import ValidationError


def validate_plain_text(text: str) -> None:
    if not text or not text.strip():
        raise ValidationError("content_empty")

    text_lower = text.lower()

    if len(text) < MIN_TEXT_LENGTH:
        raise ValidationError(
            f"content_too_short: len={len(text)} < {MIN_TEXT_LENGTH}"
        )

    if len(text_lower) < 500:
        for keyword in BLOCK_MARKERS_SOFT:
            if keyword in text_lower:
                raise ValidationError(f"soft_block:{keyword}")

    if len(text_lower) < 1000:
        for keyword in BLOCK_MARKERS_STRONG:
            if keyword in text_lower:
                raise ValidationError(f"strong_block:{keyword}")

        for keyword in BLOCK_MARKERS_UNKNOWN:
            if keyword in text_lower:
                raise ValidationError(f"unknown_content:{keyword}")
