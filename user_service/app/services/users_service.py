from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends
from pymongo.database import Database

from common.models.user import User, UserProfile, UserUpsertInput
from common.mongo.client import get_database

from ..repositories.interfaces import (
    UserRepositoryInterface,
    BookmarkRepositoryInterface,
)
from ..repositories.user_repository import UserRepository
from ..repositories.bookmark_repository import BookmarkRepository


class UsersService:
    """유저 upsert 및 프로필 조회 비즈니스 로직.

    - Repository(UserRepositoryInterface)에만 의존하고, Mongo 세부 구현은 알지 않는다.
    """

    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        bookmark_repo: BookmarkRepositoryInterface,
    ) -> None:
        self._user_repo = user_repo
        self._bookmark_repo = bookmark_repo

    def upsert_user(self, input_model: UserUpsertInput) -> UserProfile:
        existing = self._user_repo.find_by_provider_and_sub(
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

            created = self._user_repo.insert(user)
            return self._to_profile(created)

        updated = self._user_repo.update_profile(
            user_code=existing.user_code,
            email=input_model.email,
            name=input_model.name,
            profile_image=input_model.profile_image,
        )
        return self._to_profile(updated)

    def get_profile(self, user_code: str) -> UserProfile | None:
        user = self._user_repo.find_by_user_code(user_code)
        if user is None:
            return None
        return self._to_profile(user)

    def delete_user(self, user_code: str) -> bool:
        """유저와 해당 유저의 모든 북마크를 삭제한다.

        - user 가 존재하지 않으면 False 를 반환한다.
        - 존재하는 경우 북마크를 먼저 삭제하고, 이후 유저 도큐먼트를 삭제한다.
        """

        user = self._user_repo.find_by_user_code(user_code)
        if user is None:
            return False

        # 북마크는 존재하지 않아도 delete_many 결과가 0 이므로 별도 체크는 하지 않는다.
        self._bookmark_repo.delete_all_by_user_code(user_code)
        return self._user_repo.delete_by_user_code(user_code)

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

    def list_users(self, page: int, page_size: int) -> tuple[list[UserProfile], int]:
        users, total = self._user_repo.list(page, page_size)
        profiles = [self._to_profile(u) for u in users]
        return profiles, total


def get_user_repository(
    db: Database = Depends(get_database),
) -> UserRepositoryInterface:
    """FastAPI DI용 UserRepository 팩토리."""

    return UserRepository(db)


def get_bookmark_repository_for_users(
    db: Database = Depends(get_database),
) -> BookmarkRepositoryInterface:
    """UsersService 에서 사용할 BookmarkRepository DI 팩토리."""

    return BookmarkRepository(db)


def get_users_service(
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
    bookmark_repo: BookmarkRepositoryInterface = Depends(
        get_bookmark_repository_for_users
    ),
) -> UsersService:
    """FastAPI DI용 UsersService 팩토리."""

    return UsersService(user_repo=user_repo, bookmark_repo=bookmark_repo)
