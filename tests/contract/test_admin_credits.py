"""어드민 크레딧 지급 만료일 계약."""

from __future__ import annotations

from datetime import timedelta

import pytest

from techletter.core.time import to_iso_z, utcnow

pytestmark = [pytest.mark.integration, pytest.mark.contract]


@pytest.fixture
async def a_user(ctx):
    from techletter.users.service import OAuthProfile

    return await ctx.users.upsert_from_oauth(
        OAuthProfile(
            provider="google",
            provider_sub="sub-credits",
            email="credits@example.com",
            name="Credits",
        )
    )


async def test_granting_credits_allows_expiry_within_364_days(
    client, admin_headers, a_user
) -> None:
    response = await client.post(
        f"/api/v1/admin/users/{a_user.user_code}/credits",
        json={"amount": 5, "expires_at": to_iso_z(utcnow() + timedelta(days=364))},
        headers=admin_headers,
    )

    assert response.status_code == 201


async def test_granting_credits_rejects_expiry_after_max_days(
    client, admin_headers, a_user
) -> None:
    response = await client.post(
        f"/api/v1/admin/users/{a_user.user_code}/credits",
        json={"amount": 5, "expires_at": to_iso_z(utcnow() + timedelta(days=366))},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"] == {
        "field": "expires_at",
        "max_days": 365,
    }


async def test_granting_credits_rejects_past_expiry(client, admin_headers, a_user) -> None:
    response = await client.post(
        f"/api/v1/admin/users/{a_user.user_code}/credits",
        json={"amount": 5, "expires_at": to_iso_z(utcnow() - timedelta(days=1))},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"]["field"] == "expires_at"
