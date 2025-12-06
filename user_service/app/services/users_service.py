from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends
from pymongo.database import Database

from common.models.user import User, UserProfile, UserUpsertInput
from common.mongo.client import get_database

from ..repositories.interfaces import UserRepositoryInterface
from ..repositories.user_repository import UserRepository


class UsersService:
    """유저 upsert 및 프로필 조회 비즈니스 로직.

    - Repository(UserRepositoryInterface)에만 의존하고, Mongo 세부 구현은 알지 않는다.
    """

    def __init__(self, repo: UserRepositoryInterface) -> None:
        self._repo = repo

    def upsert_user(self, input_model: UserUpsertInput) -> UserProfile:
        existing = self._repo.find_by_provider_and_sub(
            provider=input_model.provider,
            provider_sub=input_model.provider_sub,
        )

        if existing is None:
            now = datetime.now(timezone.utc)
            user_code = f"{input_model.provider}:{uuid4()}"

            user = User(
                user_code=user_code,
                provider=input_model.provider,
                provider_sub=input_model.provider_sub,
                email=input_model.email,
                name=input_model.name,
                profile_image=input_model.profile_image,
                role="user",
                created_at=now,
                updated_at=now,
            )

            created = self._repo.insert(user)
            return self._to_profile(created)

        updated = self._repo.update_profile(
            user_code=existing.user_code,
            email=input_model.email,
            name=input_model.name,
            profile_image=input_model.profile_image,
        )
        return self._to_profile(updated)

    def get_profile(self, user_code: str) -> UserProfile | None:
        user = self._repo.find_by_user_code(user_code)
        if user is None:
            return None
        return self._to_profile(user)

    @staticmethod
    def _to_profile(user: User) -> UserProfile:
        return UserProfile(
            user_code=user.user_code,
            provider=user.provider,
            provider_sub=user.provider_sub,
            email=user.email,
            name=user.name,
            profile_image=user.profile_image,
            role=user.role,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


def get_user_repository(
    db: Database = Depends(get_database),
) -> UserRepositoryInterface:
    """FastAPI DI용 UserRepository 팩토리."""

    return UserRepository(db)


def get_users_service(
    repo: UserRepositoryInterface = Depends(get_user_repository),
) -> UsersService:
    """FastAPI DI용 UsersService 팩토리."""

    return UsersService(repo)
