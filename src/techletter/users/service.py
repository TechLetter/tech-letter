"""사용자 서비스.

프로필과 크레딧 잔액을 합성해 제공한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.errors import ResourceNotFoundError
from techletter.core.logging import get_logger
from techletter.users.models import User

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.pagination import Page
    from techletter.users.credits import CreditService
    from techletter.users.repositories import BookmarkRepository, UserRepository

__all__ = ["OAuthProfile", "UserProfile", "UserService"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OAuthProfile:
    provider: str
    provider_sub: str
    email: str | None = None
    name: str | None = None
    profile_image: str | None = None


@dataclass(frozen=True, slots=True)
class UserProfile:
    """`GET /me` 응답의 재료."""

    user: User
    credits_remaining: int
    credits_granted_today: int = 0


class UserService:
    def __init__(
        self,
        users: UserRepository,
        credits: CreditService,
        bookmarks: BookmarkRepository,
    ) -> None:
        self._users = users
        self._credits = credits
        self._bookmarks = bookmarks

    async def upsert_from_oauth(self, profile: OAuthProfile) -> User:
        """OAuth 로그인 결과로 유저를 만들거나 갱신한다."""
        candidate = User(
            user_code=f"{profile.provider}:{uuid.uuid4()}",
            provider=profile.provider,
            provider_sub=profile.provider_sub,
            email=profile.email,
            name=profile.name,
            profile_image=profile.profile_image,
        )
        return await self._users.upsert(candidate)

    async def get_profile(self, user_code: str) -> UserProfile:
        """프로필과 크레딧을 합쳐서 준다.

        크레딧 조회가 실패해도 프로필은 준다 — 크레딧 서비스 장애로 로그인
        상태가 깨지지 않게 하려는 것이다.
        """
        user = await self._users.get_by_user_code(user_code)
        if user is None:
            raise ResourceNotFoundError("사용자를 찾을 수 없습니다.")
        try:
            remaining = await self._credits.remaining(user_code)
        except Exception:
            logger.warning("failed to load credits", extra={"user_code": user_code})
            remaining = 0
        return UserProfile(user=user, credits_remaining=remaining)

    async def list_users(self, page: Page) -> tuple[list[UserProfile], int]:
        """어드민 목록. 크레딧을 벌크로 조회해 N+1을 피한다."""
        users, total = await self._users.list_users(page)
        remaining = await self._credits.remaining_bulk([u.user_code for u in users])
        return [
            UserProfile(user=u, credits_remaining=remaining.get(u.user_code, 0)) for u in users
        ], total

    async def delete_user(self, user_code: str) -> None:
        """유저와 딸린 데이터를 지운다(캐스케이드)."""
        user = await self._users.get_by_user_code(user_code)
        if user is None:
            raise ResourceNotFoundError("사용자를 찾을 수 없습니다.")
        await self._bookmarks.delete_by_user(user_code)
        await self._credits.delete_for_user(user_code)
        await self._users.delete(user_code)
        logger.info("user deleted", extra={"user_code": user_code})
