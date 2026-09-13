"""어드민 사용자 목록의 크레딧 계약."""

from __future__ import annotations

from datetime import timedelta

import pytest

from techletter.core.time import utcnow

pytestmark = [pytest.mark.integration, pytest.mark.contract]


async def test_admin_users_report_grants_per_user(client, ctx, admin_headers) -> None:
    from techletter.users.service import OAuthProfile

    alice = await ctx.users.upsert_from_oauth(
        OAuthProfile(provider="google", provider_sub="admin-users-alice")
    )
    bob = await ctx.users.upsert_from_oauth(
        OAuthProfile(provider="google", provider_sub="admin-users-bob")
    )
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    await ctx.db["credit_transactions"].insert_many(
        [
            {
                "user_code": alice.user_code,
                "type": "grant",
                "amount": 10,
                "created_at": day_start + timedelta(hours=1),
            },
            {
                "user_code": alice.user_code,
                "type": "admin_grant",
                "amount": 5,
                "created_at": day_start + timedelta(hours=2),
            },
            {
                "user_code": bob.user_code,
                "type": "grant",
                "amount": 10,
                "created_at": day_start - timedelta(seconds=1),
            },
        ]
    )

    response = await client.get("/api/v1/admin/users", headers=admin_headers)

    assert response.status_code == 200
    items = {item["user_code"]: item for item in response.json()["items"]}
    assert items[alice.user_code]["credits"]["granted_today"] == 15
    assert items[bob.user_code]["credits"]["granted_today"] == 0
