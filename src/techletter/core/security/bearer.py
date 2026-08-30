"""Authorization 헤더 파싱.

헤더가 없든 형식이 틀렸든 전부 `auth.required`(401)로 합친다 — 프론트는
401만 보고 동작하므로 실패 원인을 더 세분화해 알려줄 이유가 없다.
"""

from __future__ import annotations

from techletter.core.errors import AuthRequiredError

__all__ = ["extract_bearer"]

_SCHEME = "bearer"


def extract_bearer(header: str | None) -> str:
    """`Authorization: Bearer <token>`에서 토큰을 꺼낸다.

    스킴 비교는 대소문자를 무시한다 — `bearer`도 통과시킨다.
    """
    if not header:
        raise AuthRequiredError
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != _SCHEME:
        raise AuthRequiredError
    token = parts[1].strip()
    if not token:
        raise AuthRequiredError
    return token
