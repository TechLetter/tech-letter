"""Google OAuth와 토큰 교환.

프론트가 `?session=`을 읽어 교환한다. 실패도 **쿼리 없는 리다이렉트**다.
실패 사유를 URL에 실으면 사용자에게 쓸모없고 로그에는 남는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse

from techletter.api.deps import Ctx
from techletter.api.schemas import TokenIn, TokenOut
from techletter.core.logging import get_logger
from techletter.users.auth_service import OAUTH_STATE_COOKIE, GoogleOAuthError

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.get("/google/login", include_in_schema=False)
async def google_login(ctx: Ctx) -> RedirectResponse:
    start = ctx.auth.start_login()
    response = RedirectResponse(start.authorize_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        start.state,
        max_age=ctx.settings.auth.oauth_state_ttl_seconds,
        httponly=True,
        secure=ctx.settings.auth.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    ctx: Ctx, request: Request, code: str = "", state: str = ""
) -> RedirectResponse:
    auth = ctx.auth
    try:
        target = await auth.handle_callback(code, state, request.cookies.get(OAUTH_STATE_COOKIE))
    except GoogleOAuthError as exc:
        logger.warning("oauth callback failed", extra={"reason": str(exc)})
        target = auth.failure_redirect()
    except Exception:
        logger.exception("oauth callback crashed")
        target = auth.failure_redirect()

    response = RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    # state는 한 번만 쓴다. 성공이든 실패든 지운다.
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return response


@router.post("/token", response_model=TokenOut)
async def exchange_token(ctx: Ctx, body: TokenIn) -> TokenOut:
    token = await ctx.auth.exchange_session(body.session)
    return TokenOut(access_token=token, expires_in=ctx.settings.auth.jwt_ttl_seconds)
