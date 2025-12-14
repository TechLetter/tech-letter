from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from common.models.user import UserUpsertInput, UserProfile
from ..schemas.users import (
    UserUpsertRequest,
    UserUpsertResponse,
    UserProfileResponse,
    ListUsersResponse,
)
from ...services.users_service import UsersService, get_users_service

router = APIRouter()


@router.post("/upsert", response_model=UserUpsertResponse, summary="유저 upsert")
async def upsert_user(
    body: UserUpsertRequest,
    service: UsersService = Depends(get_users_service),
) -> UserUpsertResponse:
    input_model = UserUpsertInput(**body.model_dump())
    profile = service.upsert_user(input_model)
    return UserUpsertResponse(user_code=profile.user_code, role=profile.role)


@router.get(
    "/{user_code}", response_model=UserProfileResponse, summary="유저 프로필 조회"
)
async def get_user_profile(
    user_code: str,
    service: UsersService = Depends(get_users_service),
) -> UserProfileResponse:
    profile: UserProfile | None = service.get_profile(user_code)
    if profile is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserProfileResponse.from_domain(profile)


@router.delete("/{user_code}", summary="유저 삭제 (내부용)")
async def delete_user(
    user_code: str,
    service: UsersService = Depends(get_users_service),
) -> dict[str, str]:
    deleted = service.delete_user(user_code)
    if not deleted:
        raise HTTPException(status_code=404, detail="user not found")
    return {"message": "user_deleted"}


@router.get("", response_model=ListUsersResponse, summary="유저 목록 조회")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    service: UsersService = Depends(get_users_service),
) -> ListUsersResponse:
    users, total = service.list_users(page, page_size)
    return ListUsersResponse(
        total=total,
        items=[UserProfileResponse.from_domain(u) for u in users],
    )
