"""공개 API 계약."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

PAGED_KEYS = {"items", "page", "page_size", "total", "total_pages"}
POST_KEYS = {
    "id",
    "blog_id",
    "blog_name",
    "title",
    "link",
    "published_at",
    "thumbnail_url",
    "view_count",
    "summary",
    "categories",
    "tags",
    "is_bookmarked",
}


# ── 봉투 ────────────────────────────────────────────────────────────
async def test_every_list_uses_one_envelope(client, seeded) -> None:
    """모든 목록 응답이 같은 봉투를 써야 한다."""
    for path in ("/api/v1/posts", "/api/v1/blogs", "/api/v1/trends/posts"):
        body = (await client.get(path)).json()
        assert set(body) == PAGED_KEYS, path


async def test_total_pages_is_computed_for_the_client(client, seeded) -> None:
    body = (await client.get("/api/v1/posts?page_size=2")).json()

    assert body["total"] == 3
    assert body["total_pages"] == 2
    assert len(body["items"]) == 2


async def test_an_empty_result_has_zero_pages(client) -> None:
    body = (await client.get("/api/v1/posts")).json()

    assert body == {"items": [], "page": 1, "page_size": 20, "total": 0, "total_pages": 0}


async def test_filters_use_the_short_envelope(client, seeded) -> None:
    """페이지 개념이 없는 목록은 page/page_size/total_pages를 붙이지 않는다."""
    for path in ("/api/v1/filters/categories", "/api/v1/filters/tags", "/api/v1/filters/blogs"):
        body = (await client.get(path)).json()
        assert set(body) == {"items", "total"}, path


async def test_no_endpoint_returns_a_bare_array(client, seeded) -> None:
    for path in ("/api/v1/chat/suggested-questions", "/api/v1/filters/tags"):
        assert isinstance((await client.get(path)).json(), dict), path


# ── Post ────────────────────────────────────────────────────────────
async def test_post_fields_match_the_contract(client, seeded) -> None:
    item = (await client.get("/api/v1/posts")).json()["items"][0]

    assert set(item) == POST_KEYS


async def test_anonymous_requests_get_is_bookmarked_false(client, seeded) -> None:
    """키 자체가 없는 3번째 상태로 새지 않아야 한다."""
    items = (await client.get("/api/v1/posts")).json()["items"]

    assert all(item["is_bookmarked"] is False for item in items)


async def test_categories_and_tags_are_always_arrays(client, ctx, seeded) -> None:
    post = await ctx.posts.get(str(seeded["posts"][0].id))
    assert post is not None

    item = (await client.get(f"/api/v1/posts/{post.id}")).json()

    assert isinstance(item["categories"], list)
    assert isinstance(item["tags"], list)


async def test_an_empty_thumbnail_becomes_null(client, seeded) -> None:
    """빈 문자열을 그대로 주면 프론트가 깨진 이미지를 그린다."""
    items = (await client.get("/api/v1/posts?page_size=100")).json()["items"]
    first = next(item for item in items if item["title"] == "제목 0")

    assert first["thumbnail_url"] is None


async def test_timestamps_carry_an_offset_and_milliseconds(client, seeded) -> None:
    item = (await client.get("/api/v1/posts")).json()["items"][0]

    assert item["published_at"].endswith("Z")
    assert item["published_at"][-5] == "."


async def test_the_public_list_hides_unsummarized_posts(client, seeded) -> None:
    """공개 API는 요약 완료 글만 준다."""
    titles = [item["title"] for item in (await client.get("/api/v1/posts")).json()["items"]]

    assert "아직 요약 안 됨" not in titles


async def test_the_removed_status_parameter_is_ignored(client, seeded) -> None:
    body = (await client.get("/api/v1/posts?status_ai_summarized=false")).json()

    assert body["total"] == 3


async def test_an_unknown_post_is_a_typed_404(client) -> None:
    response = await client.get("/api/v1/posts/507f1f77bcf86cd799439011")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource.not_found"


async def test_a_malformed_post_id_is_also_404(client) -> None:
    assert (await client.get("/api/v1/posts/not-an-id")).status_code == 404


# ── 관용 파싱 ───────────────────────────────────────────────────────
async def test_garbage_paging_falls_back_instead_of_422(client, seeded) -> None:
    """프론트가 이 관용적 파싱 동작에 기대고 있다."""
    response = await client.get("/api/v1/posts?page=abc&page_size=xyz")

    assert response.status_code == 200
    assert response.json()["page"] == 1


async def test_empty_array_params_are_ignored(client, seeded) -> None:
    """프론트가 `categories=`를 보낸다."""
    response = await client.get("/api/v1/posts?categories=&tags=")

    assert response.status_code == 200
    assert response.json()["total"] == 3


async def test_page_size_is_capped(client, seeded) -> None:
    assert (await client.get("/api/v1/posts?page_size=99999")).json()["page_size"] == 100


async def test_a_date_only_published_to_covers_the_whole_day(client, seeded) -> None:
    """`2025-03-01`을 자정으로 보면 그날 글이 통째로 빠진다."""
    body = (await client.get("/api/v1/posts?published_to=2025-03-01")).json()

    assert body["total"] == 1


# ── 조회수 ──────────────────────────────────────────────────────────
async def test_recording_a_view_returns_204_with_no_body(client, seeded) -> None:
    post_id = str(seeded["posts"][0].id)

    response = await client.post(f"/api/v1/posts/{post_id}/views")

    assert response.status_code == 204
    assert response.content == b""


async def test_a_view_on_a_missing_post_is_404(client) -> None:
    assert (await client.post("/api/v1/posts/507f1f77bcf86cd799439011/views")).status_code == 404


# ── 블로그 · 필터 ───────────────────────────────────────────────────
async def test_public_blogs_expose_only_three_fields(client, seeded) -> None:
    item = (await client.get("/api/v1/blogs")).json()["items"][0]

    assert set(item) == {"id", "name", "url"}
    # rss_url 은 공개하지 않는다.


async def test_filter_items_carry_names_and_counts(client, seeded) -> None:
    body = (await client.get("/api/v1/filters/tags")).json()

    assert set(body["items"][0]) == {"name", "count"}
    assert body["items"][0]["count"] > 0


async def test_blog_filters_carry_an_id(client, seeded) -> None:
    item = (await client.get("/api/v1/filters/blogs")).json()["items"][0]

    assert set(item) == {"id", "name", "count"}


# ── 트렌드 ──────────────────────────────────────────────────────────
async def test_rising_tags_shape(client, seeded) -> None:
    body = (await client.get("/api/v1/trends/rising")).json()

    assert set(body) == {"period", "items", "total"}
    assert set(body["period"]) == {"from_at", "to", "previous_from", "previous_to"}
    if body["items"]:
        assert set(body["items"][0]) == {
            "tag",
            "current_count",
            "previous_count",
            "delta",
            "growth_rate",
        }


async def test_series_uses_items_not_series(client, seeded) -> None:
    body = (await client.get("/api/v1/trends/series?tags=Kafka")).json()

    assert set(body) == {"period", "items", "total"}
    assert body["items"][0]["tag"] == "Kafka"


async def test_an_unknown_period_is_a_typed_400(client) -> None:
    response = await client.get("/api/v1/trends/rising?period=7d")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "request.invalid"
    assert "30d" in response.json()["error"]["details"]["allowed"]


async def test_an_unknown_interval_is_a_typed_400(client) -> None:
    response = await client.get("/api/v1/trends/series?tags=Kafka&interval=hour")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "request.invalid"


# ── 헬스 ────────────────────────────────────────────────────────────
async def test_health_reports_ok(client) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
