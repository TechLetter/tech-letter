"""어드민 블로그 API 계약."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from techletter.content.models import Blog, Post

pytestmark = [pytest.mark.integration, pytest.mark.contract]


@pytest.mark.parametrize(
    "case",
    [
        ("?is_active=false", {"Beta"}),
        ("?is_active=true", {"Alpha"}),
        ("", {"Alpha", "Beta"}),
        ("?is_active=maybe", {"Alpha", "Beta"}),
    ],
)
async def test_listing_blogs_filters_by_active_state(
    client, admin_headers, ctx, seeded, case: tuple[str, set[str]]
) -> None:
    query, expected_names = case
    await ctx.blogs.insert(
        Blog(
            name="Beta",
            url="https://beta.test",
            rss_url="https://beta.test/rss",
            is_active=False,
        )
    )

    response = await client.get(f"/api/v1/admin/blogs{query}", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(expected_names)
    assert {item["name"] for item in body["items"]} == expected_names


async def test_activating_a_blog_returns_its_post_count(client, admin_headers, ctx) -> None:
    blog = await ctx.blogs.insert(
        Blog(
            name="Gamma",
            url="https://gamma.test",
            rss_url="https://gamma.test/rss",
            is_active=False,
        )
    )
    assert blog.id is not None
    for index in range(2):
        await ctx.posts.insert(
            Post(
                blog_id=blog.id,
                blog_name=blog.name,
                title=f"포스트 {index}",
                link=f"https://gamma.test/{index}",
                published_at=datetime(2025, 3, index + 1, tzinfo=UTC),
            )
        )

    response = await client.post(
        f"/api/v1/admin/blogs/{blog.id}/activate",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["post_count"] == 2
