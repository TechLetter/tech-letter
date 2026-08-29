"""JWT 발급·검증.

모듈명이 `jwt.py`면 PyJWT 패키지와 헷갈리므로 `tokens.py`로 둔다.

**기존 토큰과 호환되어야 한다**(제약 C3). 같은 `JWT_SECRET`과 클레임 구조를
쓰므로 컷오버 후에도 사용자가 재로그인할 필요가 없다.

현행 Go 구현(`cmd/api/auth/jwt.go`)과 맞춰야 하는 것:
- HS256, 클레임 `sub`(user_code) / `role` / `iss` / `exp`, TTL 24시간
- `iat`/`nbf`/`aud`/`jti` 없음
- `role`이 없으면 빈 문자열로 취급(에러 아님)

개선한 것:
- 알고리즘을 HS256으로 **고정**한다. 현행은 HMAC 계열이면 전부 허용했다.
- `iss`를 검증한다. 기존 토큰의 `iss`는 `tech-letter`라 그대로 통과한다.
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
    """검증 실패는 전부 `InvalidTokenError`다. 라이브러리 원문을 노출하지 않는다.

    현행 어드민 미들웨어는 jwt 라이브러리 에러를 그대로 응답에 실었다
    (ISSUE-009 #6).
    """
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
