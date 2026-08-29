"""내 정보 (04 §4.2)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from techletter.api.deps import Ctx, CurrentUser
from techletter.api.schemas import MeOut
from techletter.core.logging import get_logger

router = APIRouter(prefix="/me", tags=["me"])
logger = get_logger(__name__)


@router.get("", response_model=MeOut)
async def get_me(ctx: Ctx, user: CurrentUser) -> MeOut:
    return MeOut.of(await ctx.users.get_profile(user.user_code))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(ctx: Ctx, user: CurrentUser) -> Response:
    """계정과 딸린 데이터를 전부 지운다.

    대화 세션은 users 도메인이 모르므로 여기서 함께 지운다. 남겨 두면
    탈퇴한 사용자의 대화 내용이 DB에 그대로 남는다.
    """
    deleted_sessions = await ctx.sessions.delete_all(user.user_code)
    await ctx.users.delete_user(user.user_code)
    logger.info(
        "account deleted",
        extra={"user_code": user.user_code, "chat_sessions": deleted_sessions},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
