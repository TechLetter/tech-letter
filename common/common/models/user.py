from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class User(BaseModel):
    """유저 도메인 모델.

    - Mongo users 컬렉션과 1:1로 매핑되는 공용 모델이다.
    - provider/provider_sub 조합으로 식별하며, 내부 식별자는 user_code("<provider>:<uuid>")로 관리한다.
    """

    user_code: str = Field(alias="user_code")
    provider: str = Field(alias="provider")
    provider_sub: str = Field(alias="provider_sub")
    email: str = Field(alias="email")
    name: str = Field(alias="name")
    profile_image: str = Field(alias="profile_image")
    role: str = Field(alias="role")
    created_at: datetime = Field(alias="created_at")
    updated_at: datetime = Field(alias="updated_at")


class UserUpsertInput(BaseModel):
    """OAuth 기반 유저 upsert 입력 모델.

    - API Gateway에서 provider/sub/email/name/profile_image 를 전달받아 UserService 로 전달한다.
    """

    provider: str
    provider_sub: str
    email: str
    name: str
    profile_image: str


class UserProfile(BaseModel):
    """유저 프로필 조회 응답 모델.

    - API Gateway에서 /users/profile 응답 스키마로 재사용할 수 있도록 분리한다.
    """

    user_code: str
    provider: str
    provider_sub: str
    email: str
    name: str
    profile_image: str
    role: str
    credits: int = Field(default=0)
    created_at: datetime
    updated_at: datetime
