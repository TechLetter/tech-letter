"""프롬프트에 넣을 텍스트 자르기."""

from __future__ import annotations

__all__ = ["clip"]

ELLIPSIS = "..."


def clip(text: str, max_length: int) -> str:
    """`max_length`를 **넘지 않게** 자른다. 말줄임표 길이까지 계산에 넣는다."""
    if len(text) <= max_length:
        return text
    if max_length <= len(ELLIPSIS):
        return text[:max_length]
    return text[: max_length - len(ELLIPSIS)].rstrip() + ELLIPSIS
