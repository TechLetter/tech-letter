"""어드민 사용자·크레딧.

`user_code`가 `google:<uuid>` 형태라 경로에 들어가면 인코딩이 필요하다.
프론트가 `encodeURIComponent`를 붙이고, 여기서는 FastAPI가 디코딩한 값을 받는다.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import AdminUserOut, CreditGrantIn, CreditGrantOut, Paged
from techletter.api.schemas.query import StrQ, parse_page
from techletter.core.errors import InvalidRequestError
from techletter.core.time import parse_rfc3339_or_date, to_iso_z, utcnow

router = APIRouter(prefix="/users", tags=["admin:users"])

MAX_GRANT_DAYS = 365


@router.get("", response_model=Paged[AdminUserOut])
async def list_users(
    ctx: Ctx, _: AdminUser, page: StrQ = None, page_size: StrQ = None
) -> Paged[AdminUserOut]:
    paging = parse_page(page, page_size, default_size=50)
    profiles, total = await ctx.users.list_users(paging)
    return Paged.of_page([AdminUserOut.of(p) for p in profiles], total, paging)


@router.post(
    "/{user_code:path}/credits",
    status_code=status.HTTP_201_CREATED,
    response_model=CreditGrantOut,
)
async def grant_credits(
    ctx: Ctx, _: AdminUser, user_code: str, body: CreditGrantIn
) -> CreditGrantOut:
    # 존재하지 않는 유저에게 지급하면 아무도 못 쓰는 크레딧이 쌓인다.
    await ctx.users.get_profile(user_code)

    expires_at = parse_rfc3339_or_date(body.expires_at, end_of_day=True)
    if expires_at is None:
        raise InvalidRequestError(
            "만료 시각을 올바른 날짜로 입력해 주세요.", details={"field": "expires_at"}
        )
    if expires_at <= utcnow():
        raise InvalidRequestError(
            "만료 시각은 현재보다 뒤여야 합니다.", details={"field": "expires_at"}
        )

    await ctx.credits.admin_grant(user_code, body.amount, expires_at)
    return CreditGrantOut(user_code=user_code, amount=body.amount, expires_at=to_iso_z(expires_at))
