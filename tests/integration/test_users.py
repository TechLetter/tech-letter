"""users 도메인 — 저장소 라운드트립, 프로필 합성, 세션 교환, 북마크."""

from __future__ import annotations

from datetime import timedelta

import pytest

from techletter.core.errors import ResourceNotFoundError, SessionExpiredError
from techletter.core.pagination import Page
from techletter.core.time import utcnow
from techletter.users import (
    BookmarkRepository,
    CreditRepository,
    CreditService,
    CreditTransactionRepository,
    IdentityPolicyRepository,
    LoginSessionRepository,
    OAuthProfile,
    UserRepository,
    UserService,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def users_repo(mongo_db) -> UserRepository:
    return UserRepository(mongo_db)


@pytest.fixture
def bookmarks_repo(mongo_db) -> BookmarkRepository:
    return BookmarkRepository(mongo_db)


@pytest.fixture
def sessions_repo(mongo_db) -> LoginSessionRepository:
    return LoginSessionRepository(mongo_db)


@pytest.fixture
def user_service(mongo_db, users_repo, bookmarks_repo) -> UserService:
    credits = CreditService(
        CreditRepository(mongo_db),
        CreditTransactionRepository(mongo_db),
        IdentityPolicyRepository(mongo_db),
    )
    return UserService(users_repo, credits, bookmarks_repo)


PROFILE = OAuthProfile(
    provider="google",
    provider_sub="sub-1",
    email="a@example.com",
    name="테스터",
    profile_image="https://example.com/a.png",
)


# ── 유저 ────────────────────────────────────────────────────────────


async def test_upsert_creates_user_with_prefixed_code(user_service):
    user = await user_service.upsert_from_oauth(PROFILE)
    assert user.user_code.startswith("google:")
    assert user.email == "a@example.com"
    assert user.role == "user"


async def test_upsert_is_idempotent_and_keeps_user_code(user_service):
    first = await user_service.upsert_from_oauth(PROFILE)
    second = await user_service.upsert_from_oauth(PROFILE)
    assert first.user_code == second.user_code, "재로그인해도 user_code가 유지된다"


async def test_upsert_updates_profile_fields(user_service, users_repo):
    user = await user_service.upsert_from_oauth(PROFILE)
    await user_service.upsert_from_oauth(
        OAuthProfile(
            provider="google", provider_sub="sub-1", email="new@example.com", name="새이름"
        )
    )
    updated = await users_repo.get_by_user_code(user.user_code)
    assert updated is not None
    assert updated.email == "new@example.com"
    assert updated.name == "새이름"


async def test_upsert_preserves_admin_role(user_service, users_repo, mongo_db):
    user = await user_service.upsert_from_oauth(PROFILE)
    await mongo_db["users"].update_one({"user_code": user.user_code}, {"$set": {"role": "admin"}})
    await user_service.upsert_from_oauth(PROFILE)
    refreshed = await users_repo.get_by_user_code(user.user_code)
    assert refreshed is not None
    assert refreshed.role == "admin", "재로그인이 어드민 권한을 지우면 안 된다"


async def test_get_profile_combines_credits(user_service):
    user = await user_service.upsert_from_oauth(PROFILE)
    await user_service._credits.grant_daily(user.user_code, "google", "sub-1")
    profile = await user_service.get_profile(user.user_code)
    assert profile.user.user_code == user.user_code
    assert profile.credits_remaining == 10


async def test_get_profile_missing_user(user_service):
    with pytest.raises(ResourceNotFoundError):
        await user_service.get_profile("google:nope")


async def test_delete_user_cascades(user_service, users_repo, bookmarks_repo, mongo_db):
    user = await user_service.upsert_from_oauth(PROFILE)
    await bookmarks_repo.add(user.user_code, "post-1")
    await user_service._credits.grant_daily(user.user_code, "google", "sub-1")

    await user_service.delete_user(user.user_code)

    assert await users_repo.get_by_user_code(user.user_code) is None
    assert await mongo_db["bookmarks"].count_documents({"user_code": user.user_code}) == 0
    assert await mongo_db["credits"].count_documents({"user_code": user.user_code}) == 0


async def test_list_users_uses_bulk_credits(user_service):
    for i in range(3):
        await user_service.upsert_from_oauth(
            OAuthProfile(provider="google", provider_sub=f"sub-{i}")
        )
    profiles, total = await user_service.list_users(Page(page=1, page_size=10))
    assert total == 3
    assert len(profiles) == 3
    assert all(p.credits_remaining == 0 for p in profiles)


# ── 북마크 ──────────────────────────────────────────────────────────


async def test_bookmark_add_is_idempotent(bookmarks_repo):
    await bookmarks_repo.add("u1", "post-1")
    await bookmarks_repo.add("u1", "post-1")
    ids, total = await bookmarks_repo.list_post_ids("u1", Page())
    assert ids == ["post-1"]
    assert total == 1


async def test_bookmark_remove(bookmarks_repo):
    await bookmarks_repo.add("u1", "post-1")
    assert await bookmarks_repo.remove("u1", "post-1") is True
    assert await bookmarks_repo.remove("u1", "post-1") is False


async def test_bookmark_list_is_newest_first(bookmarks_repo, mongo_db):
    await bookmarks_repo.add("u1", "old")
    await mongo_db["bookmarks"].update_one(
        {"post_id": "old"}, {"$set": {"created_at": utcnow() - timedelta(days=1)}}
    )
    await bookmarks_repo.add("u1", "new")
    ids, _ = await bookmarks_repo.list_post_ids("u1", Page())
    assert ids == ["new", "old"]


async def test_filter_bookmarked(bookmarks_repo):
    await bookmarks_repo.add("u1", "post-1")
    await bookmarks_repo.add("u1", "post-2")
    result = await bookmarks_repo.filter_bookmarked("u1", ["post-1", "post-3"])
    assert result == {"post-1"}


async def test_filter_bookmarked_is_scoped_to_user(bookmarks_repo):
    await bookmarks_repo.add("u1", "post-1")
    assert await bookmarks_repo.filter_bookmarked("u2", ["post-1"]) == set()


async def test_filter_bookmarked_empty_input(bookmarks_repo):
    assert await bookmarks_repo.filter_bookmarked("u1", []) == set()


# ── 로그인 세션 ──────────────────────────────────────────────────────


async def test_login_session_roundtrip(sessions_repo):
    await sessions_repo.create("sid-1", "jwt-token", 60)
    assert await sessions_repo.consume("sid-1") == "jwt-token"


async def test_login_session_is_single_use(sessions_repo):
    await sessions_repo.create("sid-1", "jwt-token", 60)
    await sessions_repo.consume("sid-1")
    assert await sessions_repo.consume("sid-1") is None


async def test_login_session_unknown_id(sessions_repo):
    assert await sessions_repo.consume("nope") is None


async def test_expired_session_is_rejected_even_before_ttl_sweep(sessions_repo, mongo_db):
    """TTL 인덱스는 최대 60초 늦게 지운다. 만료를 직접 확인해야 한다."""
    await sessions_repo.create("sid-1", "jwt-token", 60)
    await mongo_db["login_sessions"].update_one(
        {"session_id": "sid-1"}, {"$set": {"expires_at": utcnow() - timedelta(seconds=1)}}
    )
    assert await sessions_repo.consume("sid-1") is None


async def test_exchange_session_rejects_blank(mongo_db, user_service, sessions_repo):
    """빈 문자열이 와도 500으로 죽으면 안 된다."""
    from tests.factories import make_auth_settings

    from techletter.users.auth_service import AuthService

    auth = AuthService(
        make_auth_settings(),
        user_service,
        user_service._credits,
        sessions_repo,
    )
    for value in ("", "   "):
        with pytest.raises(SessionExpiredError):
            await auth.exchange_session(value)
