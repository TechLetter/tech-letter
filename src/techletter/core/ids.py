"""식별자 유틸."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from bson import ObjectId

__all__ = ["is_object_id", "random_token", "to_object_id"]

_HEX24 = frozenset("0123456789abcdef")


def is_object_id(value: str | None) -> bool:
    """24자리 hex인지 검사한다. bson import 없이 라우팅 단계에서 쓴다."""
    if not value or len(value) != 24:
        return False
    return all(c in _HEX24 for c in value.lower())


def to_object_id(value: str) -> ObjectId | None:
    """유효하면 ObjectId, 아니면 None. 예외를 던지지 않는다."""
    # bson은 pymongo에 딸린 무거운 모듈이라 필요할 때만 올린다.
    from bson import ObjectId  # noqa: PLC0415
    from bson.errors import InvalidId  # noqa: PLC0415

    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def random_token(nbytes: int = 16) -> str:
    """OAuth state / 로그인 세션 ID용 URL-safe 난수."""
    return secrets.token_urlsafe(nbytes)
