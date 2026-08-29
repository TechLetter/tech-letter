"""FastAPI 의존성.

컨테이너는 앱 수명주기에서 만들어 `app.state`에 둔다. 요청마다 다시 만들지
않는다 — 현행은 요청마다 Mongo 클라이언트를 새로 열었다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

# 실제 import여야 한다. `Annotated["Container", ...]`처럼 문자열로 두면 FastAPI가
# 타입을 못 풀어 `ctx`를 쿼리 파라미터로 착각한다.
from techletter.container import Container
from techletter.core.errors import AuthForbiddenError, AuthRequiredError, InvalidTokenError
from techletter.core.security.bearer import extract_bearer
from techletter.core.security.tokens import TokenClaims, verify_token

__all__ = [
    "AdminUser",
    "Ctx",
    "CurrentUser",
    "MaybeUser",
    "admin_user",
    "container",
    "current_user",
    "optional_user",
]


def container(request: Request) -> Container:
    return request.app.state.container


Ctx = Annotated[Container, Depends(container)]


def _claims(request: Request) -> TokenClaims:
    settings = container(request).settings.auth
    return verify_token(settings, extract_bearer(request.headers.get("Authorization")))


def optional_user(request: Request) -> TokenClaims | None:
    """토큰이 있으면 해석하고, 없거나 틀리면 익명으로 본다.

    공개 목록에서 `is_bookmarked`를 채우기 위한 것이다. 만료된 토큰으로
    포스트 목록을 못 보게 만들 이유가 없다.
    """
    try:
        return _claims(request)
    except (AuthRequiredError, InvalidTokenError):
        return None


def current_user(request: Request) -> TokenClaims:
    return _claims(request)


def admin_user(request: Request) -> TokenClaims:
    claims = _claims(request)
    if claims.role != "admin":
        raise AuthForbiddenError
    return claims


MaybeUser = Annotated[TokenClaims | None, Depends(optional_user)]
CurrentUser = Annotated[TokenClaims, Depends(current_user)]
AdminUser = Annotated[TokenClaims, Depends(admin_user)]
