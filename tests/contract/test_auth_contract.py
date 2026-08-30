"""인증·나·북마크 계약."""

from __future__ import annotations

import pytest
from tests.contract.conftest import USER_CODE

pytestmark = pytest.mark.integration


@pytest.fixture
async def registered(ctx):
    from techletter.users.service import OAuthProfile

    return await ctx.users.upsert_from_oauth(
        OAuthProfile(
            provider="google",
            provider_sub="sub-1",
            email="alice@example.com",
            name="Alice",
            profile_image="https://img.test/a.png",
        )
    )


@pytest.fixture
def headers_for(contract_settings):
    from techletter.core.security.tokens import issue_token

    def make(user_code: str, role: str = "user") -> dict[str, str]:
        return {"Authorization": f"Bearer {issue_token(contract_settings.auth, user_code, role)}"}

    return make


# ── 인증 실패 ───────────────────────────────────────────────────────
async def test_no_token_is_auth_required(client) -> None:
    response = await client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.required"


@pytest.mark.parametrize(
    "header", ["Bearer", "Bearer   ", "Token abc", "abc", "Basic dXNlcjpwYXNz"]
)
async def test_malformed_headers_are_auth_required(client, header: str) -> None:
    response = await client.get("/api/v1/me", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.required"


async def test_a_bad_signature_is_invalid_token(client) -> None:
    forged = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.bad-signature"

    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_token"


async def test_lowercase_bearer_is_accepted(client, registered, headers_for) -> None:
    header = headers_for(registered.user_code)["Authorization"].replace("Bearer", "bearer")

    response = await client.get("/api/v1/me", headers={"Authorization": header})

    assert response.status_code == 200


# ── /me ─────────────────────────────────────────────────────────────
async def test_me_shape(client, registered, headers_for) -> None:
    body = (await client.get("/api/v1/me", headers=headers_for(registered.user_code))).json()

    assert set(body) == {
        "user_code",
        "email",
        "name",
        "profile_image",
        "role",
        "credits",
        "created_at",
        "updated_at",
    }


async def test_credits_are_an_object_not_an_integer(client, registered, headers_for) -> None:
    body = (await client.get("/api/v1/me", headers=headers_for(registered.user_code))).json()

    assert isinstance(body["credits"], dict)
    assert set(body["credits"]) == {"remaining", "granted_today"}


async def test_internal_identifiers_are_not_exposed(client, registered, headers_for) -> None:
    body = (await client.get("/api/v1/me", headers=headers_for(registered.user_code))).json()

    assert "provider" not in body
    assert "provider_sub" not in body


async def test_me_for_an_unknown_user_is_404(client, headers_for) -> None:
    response = await client.get("/api/v1/me", headers=headers_for("google:ghost"))

    assert response.status_code == 404


async def test_deleting_me_returns_204_and_removes_chat_sessions(
    client, ctx, registered, headers_for
) -> None:
    headers = headers_for(registered.user_code)
    await ctx.sessions.create(registered.user_code, "질문")

    response = await client.delete("/api/v1/me", headers=headers)

    assert response.status_code == 204
    assert response.content == b""
    from techletter.core.pagination import Page

    _, remaining = await ctx.sessions.list(registered.user_code, Page(1, 10))
    assert remaining == 0


# ── 토큰 교환 ───────────────────────────────────────────────────────
async def test_exchanging_an_unknown_session_is_a_typed_400(client) -> None:
    response = await client.post("/api/v1/auth/token", json={"session": "nope"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "auth.session_expired"


async def test_a_blank_session_does_not_crash(client) -> None:
    """공백뿐인 세션 값이 500으로 죽으면 안 된다."""
    response = await client.post("/api/v1/auth/token", json={"session": " "})

    assert response.status_code == 400


async def test_a_valid_session_returns_a_bearer_token(client, ctx, registered) -> None:
    from techletter.core.security.tokens import issue_token

    token = issue_token(ctx.settings.auth, registered.user_code)
    await ctx.db["login_sessions"].insert_one(
        {
            "session_id": "one-time",
            "jwt_token": token,
            "expires_at": __import__("datetime").datetime.now(__import__("datetime").UTC)
            + __import__("datetime").timedelta(seconds=300),
        }
    )

    body = (await client.post("/api/v1/auth/token", json={"session": "one-time"})).json()

    assert body["access_token"] == token
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == ctx.settings.auth.jwt_ttl_seconds


async def test_a_session_can_only_be_exchanged_once(client, ctx, registered) -> None:
    from datetime import UTC, datetime, timedelta

    from techletter.core.security.tokens import issue_token

    await ctx.db["login_sessions"].insert_one(
        {
            "session_id": "one-time",
            "jwt_token": issue_token(ctx.settings.auth, registered.user_code),
            "expires_at": datetime.now(UTC) + timedelta(seconds=300),
        }
    )

    first = await client.post("/api/v1/auth/token", json={"session": "one-time"})
    second = await client.post("/api/v1/auth/token", json={"session": "one-time"})

    assert first.status_code == 200
    assert second.status_code == 400


async def test_login_redirects_and_sets_a_state_cookie(client) -> None:
    response = await client.get("/api/v1/auth/google/login")

    assert response.status_code == 302
    assert "accounts.google.com" in response.headers["location"]
    assert "oauth_state=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


async def test_a_callback_without_state_redirects_without_a_query(client) -> None:
    """실패 사유를 URL에 싣지 않는다."""
    response = await client.get("/api/v1/auth/google/callback?code=x&state=y")

    assert response.status_code == 302
    assert "?" not in response.headers["location"]


# ── 북마크 ──────────────────────────────────────────────────────────
async def test_bookmarks_require_authentication(client) -> None:
    assert (await client.get("/api/v1/bookmarks")).status_code == 401


async def test_adding_a_bookmark_returns_201(client, seeded, user_headers) -> None:
    post_id = str(seeded["posts"][0].id)

    response = await client.post(
        "/api/v1/bookmarks", json={"post_id": post_id}, headers=user_headers
    )

    assert response.status_code == 201
    assert set(response.json()) == {"post_id", "created_at"}


async def test_bookmarking_an_unknown_post_is_404(client, user_headers) -> None:
    response = await client.post(
        "/api/v1/bookmarks",
        json={"post_id": "507f1f77bcf86cd799439011"},
        headers=user_headers,
    )

    assert response.status_code == 404


async def test_bookmarking_twice_is_idempotent(client, seeded, user_headers) -> None:
    post_id = str(seeded["posts"][0].id)
    payload = {"post_id": post_id}

    first = await client.post("/api/v1/bookmarks", json=payload, headers=user_headers)
    second = await client.post("/api/v1/bookmarks", json=payload, headers=user_headers)

    assert first.status_code == 201
    assert second.status_code == 201
    body = (await client.get("/api/v1/bookmarks", headers=user_headers)).json()
    assert body["total"] == 1


async def test_the_bookmark_list_marks_every_post(client, seeded, user_headers) -> None:
    for post in seeded["posts"][:2]:
        await client.post("/api/v1/bookmarks", json={"post_id": str(post.id)}, headers=user_headers)

    body = (await client.get("/api/v1/bookmarks", headers=user_headers)).json()

    assert body["total"] == 2
    assert all(item["is_bookmarked"] is True for item in body["items"])


async def test_a_logged_in_list_shows_bookmark_state(client, seeded, user_headers) -> None:
    marked = str(seeded["posts"][0].id)
    await client.post("/api/v1/bookmarks", json={"post_id": marked}, headers=user_headers)

    items = (await client.get("/api/v1/posts", headers=user_headers)).json()["items"]

    by_id = {item["id"]: item["is_bookmarked"] for item in items}
    assert by_id[marked] is True
    assert sum(by_id.values()) == 1


async def test_removing_a_bookmark_returns_204(client, seeded, user_headers) -> None:
    post_id = str(seeded["posts"][0].id)
    await client.post("/api/v1/bookmarks", json={"post_id": post_id}, headers=user_headers)

    response = await client.delete(f"/api/v1/bookmarks/{post_id}", headers=user_headers)

    assert response.status_code == 204


async def test_removing_a_missing_bookmark_is_404(client, seeded, user_headers) -> None:
    response = await client.delete(
        f"/api/v1/bookmarks/{seeded['posts'][0].id}", headers=user_headers
    )

    assert response.status_code == 404


async def test_bookmarks_are_per_user(client, seeded, user_headers, headers_for) -> None:
    post_id = str(seeded["posts"][0].id)
    await client.post("/api/v1/bookmarks", json={"post_id": post_id}, headers=user_headers)

    other = (await client.get("/api/v1/bookmarks", headers=headers_for("google:bob"))).json()

    assert other["total"] == 0
    assert USER_CODE != "google:bob"
