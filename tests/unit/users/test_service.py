"""사용자 서비스의 크레딧 합성."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from techletter.core.pagination import Page
from techletter.users.credits import CreditService
from techletter.users.models import User
from techletter.users.repositories import BookmarkRepository, UserRepository
from techletter.users.service import UserService

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


class FakeUsers:
    def __init__(self, users: list[User]) -> None:
        self._users = {user.user_code: user for user in users}

    async def get_by_user_code(self, user_code: str) -> User | None:
        return self._users.get(user_code)

    async def list_users(self, page: Page) -> tuple[list[User], int]:
        users = list(self._users.values())[page.skip : page.skip + page.page_size]
        return users, len(self._users)


class FakeCredits:
    def __init__(self, records: dict[str, list[tuple[str, int, datetime]]]) -> None:
        self._records = records
        self.bulk_calls = 0

    async def remaining(self, user_code: str) -> int:
        return 0

    async def remaining_bulk(self, user_codes: list[str]) -> dict[str, int]:
        return dict.fromkeys(user_codes, 0)

    async def granted_amount_on(
        self, user_code: str, day_start: datetime, day_end: datetime
    ) -> int:
        return self._sum(user_code, day_start, day_end)

    async def granted_amount_on_bulk(
        self, user_codes: list[str], day_start: datetime, day_end: datetime
    ) -> dict[str, int]:
        self.bulk_calls += 1
        return {user_code: self._sum(user_code, day_start, day_end) for user_code in user_codes}

    def _sum(self, user_code: str, day_start: datetime, day_end: datetime) -> int:
        return sum(
            amount
            for tx_type, amount, created_at in self._records.get(user_code, [])
            if tx_type in {"grant", "admin_grant"} and day_start <= created_at < day_end
        )


class FakeBookmarks:
    pass


def make_user(user_code: str) -> User:
    return User(user_code=user_code, provider="google", provider_sub=user_code)


def make_service(
    records: dict[str, list[tuple[str, int, datetime]]],
) -> tuple[UserService, FakeCredits]:
    users = [make_user(user_code) for user_code in records]
    credits = FakeCredits(records)
    return UserService(
        cast(UserRepository, FakeUsers(users)),
        cast(CreditService, credits),
        cast(BookmarkRepository, FakeBookmarks()),
    ), credits


async def test_get_profile_counts_only_todays_grants(monkeypatch) -> None:
    day_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    service, _ = make_service(
        {
            "google:alice": [
                ("grant", 10, day_start + timedelta(minutes=1)),
                ("admin_grant", 5, day_start + timedelta(hours=1)),
                ("consume", -1, day_start + timedelta(hours=2)),
                ("grant", 10, day_start - timedelta(seconds=1)),
            ]
        }
    )
    monkeypatch.setattr("techletter.users.service.utcnow", lambda: NOW)

    profile = await service.get_profile("google:alice")

    assert profile.credits_granted_today == 15


async def test_list_users_uses_one_bulk_grant_lookup(monkeypatch) -> None:
    day_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    service, credits = make_service(
        {
            "google:alice": [
                ("grant", 10, day_start + timedelta(minutes=1)),
                ("admin_grant", 5, day_start + timedelta(hours=1)),
            ],
            "google:bob": [("grant", 10, day_start - timedelta(days=1))],
        }
    )
    monkeypatch.setattr("techletter.users.service.utcnow", lambda: NOW)

    profiles, total = await service.list_users(Page(page=1, page_size=10))

    assert total == 2
    assert {profile.user.user_code: profile.credits_granted_today for profile in profiles} == {
        "google:alice": 15,
        "google:bob": 0,
    }
    assert credits.bulk_calls == 1
