"""JWT 발급·검증.

모듈명이 `jwt.py`면 PyJWT 패키지와 헷갈리므로 `tokens.py`로 둔다.

**이미 발급된 토큰과 호환돼야 한다** — 클레임 구조나 시크릿을 바꾸면 로그인
중인 사용자가 전부 튕겨나간다.
- 알고리즘은 HS256으로 고정한다.
- 클레임: `sub`(user_code) / `role` / `iss` / `exp`, TTL 24시간. `iat`/`nbf`/
  `aud`/`jti`는 없다.
- `role`이 없으면 빈 문자열로 취급한다(에러 아님).
- `iss`를 검증한다 — 값은 `tech-letter`로 고정.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import jwt

from techletter.core.errors import InvalidTokenError
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from techletter.settings import AuthSettings

__all__ = ["ROLE_ADMIN", "ROLE_USER", "TokenClaims", "issue_token", "verify_token"]

ALGORITHM = "HS256"
ROLE_USER = "user"
ROLE_ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_code: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


def issue_token(settings: AuthSettings, user_code: str, role: str = ROLE_USER) -> str:
    expires = utcnow() + timedelta(seconds=settings.jwt_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": user_code,
        "role": role,
        "iss": settings.jwt_issuer,
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def verify_token(settings: AuthSettings, token: str) -> TokenClaims:
    """검증 실패는 전부 `InvalidTokenError`다. 라이브러리 원문을 노출하지 않는다."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError from exc

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidTokenError
    role = payload.get("role")
    return TokenClaims(user_code=subject, role=role if isinstance(role, str) else "")
