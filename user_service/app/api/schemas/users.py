from __future__ import annotations

from pydantic import BaseModel

from common.models.user import UserProfile
from common.types.datetime import UtcDateTime


class UserUpsertRequest(BaseModel):
    provider: str
    provider_sub: str
    email: str
    name: str
    profile_image: str


class UserUpsertResponse(BaseModel):
    user_code: str
    role: str


class UserProfileResponse(BaseModel):
    user_code: str
    provider: str
    provider_sub: str
    email: str
    name: str
    profile_image: str
    role: str
    credits: int
    created_at: UtcDateTime
    updated_at: UtcDateTime

    @classmethod
    def from_domain(cls, user: UserProfile) -> "UserProfileResponse":
        return cls(
            user_code=user.user_code,
            provider=user.provider,
            provider_sub=user.provider_sub,
            email=user.email,
            name=user.name,
            profile_image=user.profile_image,
            role=user.role,
            credits=user.credits,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class ListUsersResponse(BaseModel):
    total: int
    items: list[UserProfileResponse]
