"""Authorization 헤더 파싱.

현행(`cmd/api/auth/http.go`)은 실패 원인을 세 가지 에러 코드로 구분했다.
v2에서는 전부 `auth.required`(401)로 합친다 — 프론트가 401만 보고 동작하고,
"헤더가 없는지 형식이 틀린지"를 클라이언트에 알려줄 이유가 없다.
"""

from __future__ import annotations

from techletter.core.errors import AuthRequiredError

__all__ = ["extract_bearer"]

_SCHEME = "bearer"


def extract_bearer(header: str | None) -> str:
    """`Authorization: Bearer <token>`에서 토큰을 꺼낸다.

    스킴 비교는 대소문자를 무시한다(현행 동작 유지 — `bearer`도 통과했다).
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
