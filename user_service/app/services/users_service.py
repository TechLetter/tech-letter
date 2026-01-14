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
    CreditRepositoryInterface,
    ChatSessionRepositoryInterface,
)
from ..repositories.user_repository import UserRepository
from ..repositories.bookmark_repository import BookmarkRepository
from ..repositories.credit_repository import CreditRepository
from ..repositories.chat_session_repository import ChatSessionRepository


class UsersService:
    """유저 upsert 및 프로필 조회 비즈니스 로직.

    - Repository(UserRepositoryInterface)에만 의존하고, Mongo 세부 구현은 알지 않는다.
    """

    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        bookmark_repo: BookmarkRepositoryInterface,
        credit_repo: CreditRepositoryInterface,
        chat_session_repo: ChatSessionRepositoryInterface,
    ) -> None:
        self._user_repo = user_repo
        self._bookmark_repo = bookmark_repo
        self._credit_repo = credit_repo
        self._chat_session_repo = chat_session_repo

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
        # 크레딧 정보 조회
        credit_summary = self._credit_repo.get_summary(user_code)
        return self._to_profile(user, credits=credit_summary.total_remaining)

    def list_users(self, page: int, page_size: int) -> tuple[list[UserProfile], int]:
        """유저 목록 조회. 크레딧 정보를 벌크 조회로 포함한다."""
        users, total = self._user_repo.list(page, page_size)

        # 크레딧 볼크 조회 (N+1 방지)
        user_codes = [u.user_code for u in users]
        credits_map = self._credit_repo.get_summary_bulk(user_codes)

        profiles = [
            self._to_profile(u, credits=credits_map.get(u.user_code, 0)) for u in users
        ]
        return profiles, total

    def delete_user(self, user_code: str) -> bool:
        """유저 삭제. 연관된 북마크, 크레딧, 채팅 세션도 함께 삭제한다."""
        # 1. 북마크 삭제
        self._bookmark_repo.delete_by_user(user_code)

        # 2. 크레딧 삭제
        self._credit_repo.delete_by_user(user_code)

        # 3. 채팅 세션 삭제
        self._chat_session_repo.delete_by_user(user_code)

        # 4. 유저 프로필 삭제
        return self._user_repo.delete(user_code)

    @staticmethod
    def _to_profile(user: User, credits: int = 0) -> UserProfile:
        return UserProfile(
            user_code=user.user_code,
            provider=user.provider,
            provider_sub=user.provider_sub,
            email=user.email,
            name=user.name,
            profile_image=user.profile_image,
            role=user.role,
            credits=credits,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


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


def get_credit_repository_for_users(
    db: Database = Depends(get_database),
) -> CreditRepositoryInterface:
    """UsersService에서 사용할 CreditRepository DI 팩토리."""

    return CreditRepository(db)


def get_chat_session_repository_for_users(
    db: Database = Depends(get_database),
) -> ChatSessionRepositoryInterface:
    """UsersService에서 사용할 ChatSessionRepository DI 팩토리."""

    return ChatSessionRepository(db)


def get_users_service(
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
    bookmark_repo: BookmarkRepositoryInterface = Depends(
        get_bookmark_repository_for_users
    ),
    credit_repo: CreditRepositoryInterface = Depends(get_credit_repository_for_users),
    chat_session_repo: ChatSessionRepositoryInterface = Depends(
        get_chat_session_repository_for_users
    ),
) -> UsersService:
    """FastAPI DI용 UsersService 팩토리."""

    return UsersService(
        user_repo=user_repo,
        bookmark_repo=bookmark_repo,
        credit_repo=credit_repo,
        chat_session_repo=chat_session_repo,
    )
