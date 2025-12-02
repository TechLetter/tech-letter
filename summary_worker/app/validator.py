from __future__ import annotations


class ContentValidationError(Exception):
    pass


_STRONG_BLOCK_KEYWORDS = {
    "verify you are human",
    "i'm not a robot",
    "bot check",
    "access denied",
    "security check",
    "cloudflare",
    "just a moment",
    "redirecting",
    "loading...",
    "checking your browser",
    "refresh the page",
    "enable javascript",
    "enable javascript and cookies to continue",
    "apologies, but something went wrong on our end",  # medium
}


_SOFT_BLOCK_KEYWORDS = {
    "not found",
    "forbidden",
    "internal server error",
    "bad request",
    "gateway timeout",
}


def validate_plain_text(text: str) -> None:
    if not text or not text.strip():
        raise ContentValidationError("content_empty")

    text_lower = text.lower()

    if len(text_lower) < 50:
        raise ContentValidationError("content_too_short")

    if len(text_lower) < 200:
        for keyword in _STRONG_BLOCK_KEYWORDS:
            if keyword in text_lower:
                raise ContentValidationError(f"strong_block:{keyword}")

    if len(text_lower) < 300:
        for keyword in _SOFT_BLOCK_KEYWORDS:
            if keyword in text_lower:
                raise ContentValidationError(f"soft_block:{keyword}")
