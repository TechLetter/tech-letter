"""사용자·인증·북마크 DTO."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from techletter.core.time import to_iso_z

if TYPE_CHECKING:  # pragma: no cover
    from techletter.users.service import UserProfile

__all__ = [
    "AdminUserOut",
    "BookmarkIn",
    "BookmarkOut",
    "CreditGrantIn",
    "CreditGrantOut",
    "CreditsOut",
    "MeOut",
    "TokenIn",
    "TokenOut",
]


class CreditsOut(BaseModel):
    remaining: int
    granted_today: int = 0


class MeOut(BaseModel):
    user_code: str
    email: str | None
    name: str | None
    profile_image: str | None
    role: str
    credits: CreditsOut
    created_at: str | None
    updated_at: str | None

    @classmethod
    def of(cls, profile: UserProfile) -> MeOut:
        user = profile.user
        return cls(
            user_code=user.user_code,
            email=user.email,
            name=user.name,
            profile_image=user.profile_image,
            role=user.role,
            credits=CreditsOut(
                remaining=profile.credits_remaining,
                granted_today=profile.credits_granted_today,
            ),
            created_at=to_iso_z(user.created_at),
            updated_at=to_iso_z(user.updated_at),
        )
        # provider / provider_sub 는 내보내지 않는다.


class AdminUserOut(BaseModel):
    user_code: str
    email: str | None
    name: str | None
    role: str
    credits: CreditsOut
    created_at: str | None
    updated_at: str | None

    @classmethod
    def of(cls, profile: UserProfile) -> AdminUserOut:
        user = profile.user
        return cls(
            user_code=user.user_code,
            email=user.email,
            name=user.name,
            role=user.role,
            credits=CreditsOut(remaining=profile.credits_remaining),
            created_at=to_iso_z(user.created_at),
            updated_at=to_iso_z(user.updated_at),
        )


class TokenIn(BaseModel):
    session: str = Field(min_length=1)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class BookmarkIn(BaseModel):
    post_id: str = Field(min_length=1)


class BookmarkOut(BaseModel):
    post_id: str
    created_at: str | None


class CreditGrantIn(BaseModel):
    amount: int = Field(gt=0, le=1000)
    expires_at: str | None = None


class CreditGrantOut(BaseModel):
    user_code: str
    amount: int
    expires_at: str | None
