"""어드민 계약."""

from __future__ import annotations

from datetime import timedelta

import pytest

from techletter.core.time import to_iso_z, utcnow

pytestmark = pytest.mark.integration

ADMIN_PATHS = [
    ("GET", "/api/v1/admin/posts"),
    ("GET", "/api/v1/admin/blogs"),
    ("GET", "/api/v1/admin/users"),
    ("GET", "/api/v1/admin/suggested-questions"),
    ("GET", "/api/v1/admin/jobs"),
    ("GET", "/api/v1/admin/jobs/stats"),
    ("GET", "/api/v1/admin/llm-models"),
    ("GET", "/api/v1/admin/backfill/summary"),
]


# ── 권한 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(("method", "path"), ADMIN_PATHS)
async def test_admin_paths_reject_anonymous(client, method: str, path: str) -> None:
    response = await client.request(method, path)

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), ADMIN_PATHS)
async def test_admin_paths_reject_plain_users(client, user_headers, method: str, path: str) -> None:
    response = await client.request(method, path, headers=user_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "auth.forbidden"


# ── 포스트 ──────────────────────────────────────────────────────────
async def test_admin_post_shape(client, admin_headers, seeded) -> None:
    item = (await client.get("/api/v1/admin/posts", headers=admin_headers)).json()["items"][0]

    assert set(item) == {
        "id",
        "title",
        "link",
        "blog_id",
        "blog_name",
        "published_at",
        "thumbnail_url",
        "view_count",
        "status",
        "ai_summary",
        "embedding",
        "created_at",
        "updated_at",
    }
    # DB는 `aisummary`/`ai_summarized`, 계약은 `ai_summary`/`summarized`다.
    assert "aisummary" not in item
    assert set(item["status"]) == {"summarized", "embedded", "failed_reason"}


async def test_admin_posts_include_unsummarized_ones(client, admin_headers, seeded) -> None:
    body = (await client.get("/api/v1/admin/posts", headers=admin_headers)).json()

    assert body["total"] == 4


async def test_admin_posts_can_filter_by_status(client, admin_headers, seeded) -> None:
    body = (await client.get("/api/v1/admin/posts?summarized=false", headers=admin_headers)).json()

    assert body["total"] == 1
    assert body["items"][0]["ai_summary"] is None


async def test_admin_posts_can_search(client, admin_headers, seeded) -> None:
    body = (await client.get("/api/v1/admin/posts?q=제목 1", headers=admin_headers)).json()

    assert body["total"] == 1


async def test_creating_a_post_returns_201_and_queues_a_summary(
    client, admin_headers, ctx, seeded
) -> None:
    response = await client.post(
        "/api/v1/admin/posts",
        json={
            "blog_id": str(seeded["blog"].id),
            "title": "수동 등록",
            "link": "https://alpha.test/manual",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["status"]["summarized"] is False
    assert await ctx.db["jobs"].count_documents({"type": "summary.requested"}) == 1


async def test_a_duplicate_link_is_409_with_a_field(client, admin_headers, seeded) -> None:
    payload = {
        "blog_id": str(seeded["blog"].id),
        "title": "중복",
        "link": seeded["posts"][0].link,
    }

    response = await client.post("/api/v1/admin/posts", json=payload, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "resource.conflict"
    assert response.json()["error"]["details"]["field"] == "link"


async def test_deleting_a_post_returns_204_and_queues_vector_cleanup(
    client, admin_headers, ctx, seeded
) -> None:
    post_id = str(seeded["posts"][0].id)

    response = await client.delete(f"/api/v1/admin/posts/{post_id}", headers=admin_headers)

    assert response.status_code == 204
    job = await ctx.db["jobs"].find_one({"type": "embedding.delete_requested"})
    assert job is not None
    assert job["payload"]["post_ids"] == [post_id]


async def test_retriggering_a_summary_is_202_with_a_job_id(client, admin_headers, seeded) -> None:
    post_id = str(seeded["posts"][0].id)

    response = await client.post(f"/api/v1/admin/posts/{post_id}/summarize", headers=admin_headers)

    assert response.status_code == 202
    assert response.json()["job_id"]


# ── 블로그 ──────────────────────────────────────────────────────────
async def test_admin_blog_shape(client, admin_headers, seeded) -> None:
    item = (await client.get("/api/v1/admin/blogs", headers=admin_headers)).json()["items"][0]

    assert {"rss_url", "post_count", "last_fetch_error", "is_active"} <= set(item)
    assert item["post_count"] == 4


async def test_admin_blogs_include_inactive_ones(client, admin_headers, ctx, seeded) -> None:
    """자동 비활성화된 피드를 찾는 것이 이 화면의 목적이다."""
    assert seeded["blog"].id is not None
    await ctx.blogs.deactivate(seeded["blog"].id, "auto-disabled")

    body = (await client.get("/api/v1/admin/blogs", headers=admin_headers)).json()

    assert body["total"] == 1
    assert body["items"][0]["is_active"] is False


async def test_creating_a_blog_returns_201(client, admin_headers) -> None:
    response = await client.post(
        "/api/v1/admin/blogs",
        json={"name": "Beta", "url": "https://beta.test/", "rss_url": "https://beta.test/rss"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["url"] == "https://beta.test"


async def test_a_duplicate_rss_url_is_409_with_the_field(client, admin_headers, seeded) -> None:
    response = await client.post(
        "/api/v1/admin/blogs",
        json={"name": "Copy", "url": "https://other.test", "rss_url": seeded["blog"].rss_url},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["details"]["field"] == "rss_url"


async def test_an_unknown_blog_type_is_400(client, admin_headers) -> None:
    response = await client.post(
        "/api/v1/admin/blogs",
        json={
            "name": "X",
            "url": "https://x.test",
            "rss_url": "https://x.test/rss",
            "blog_type": "podcast",
        },
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"]["field"] == "blog_type"


async def test_updating_a_blog_keeps_the_fetch_history(client, admin_headers, ctx, seeded) -> None:
    """전체 교체로 처리하면 `last_fetched_at`이 날아간다."""
    assert seeded["blog"].id is not None
    await ctx.blogs.record_fetch_result(seeded["blog"].id, None)

    response = await client.put(
        f"/api/v1/admin/blogs/{seeded['blog'].id}",
        json={
            "name": "Alpha Renamed",
            "url": seeded["blog"].url,
            "rss_url": seeded["blog"].rss_url,
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Alpha Renamed"
    assert response.json()["last_fetched_at"] is not None


async def test_deleting_a_blog_reports_removed_posts(client, admin_headers, seeded) -> None:
    response = await client.delete(
        f"/api/v1/admin/blogs/{seeded['blog'].id}?delete_posts=true", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_posts": 4}


# ── 사용자 · 크레딧 ─────────────────────────────────────────────────
@pytest.fixture
async def a_user(ctx):
    from techletter.users.service import OAuthProfile

    return await ctx.users.upsert_from_oauth(
        OAuthProfile(provider="google", provider_sub="sub-1", email="a@b.c", name="A")
    )


async def test_admin_user_shape(client, admin_headers, a_user) -> None:
    item = (await client.get("/api/v1/admin/users", headers=admin_headers)).json()["items"][0]

    assert set(item) == {
        "user_code",
        "email",
        "name",
        "role",
        "credits",
        "created_at",
        "updated_at",
    }
    assert set(item["credits"]) == {"remaining", "granted_today"}


async def test_granting_credits_returns_201(client, admin_headers, ctx, a_user) -> None:
    expires = to_iso_z(utcnow() + timedelta(days=7))

    response = await client.post(
        f"/api/v1/admin/users/{a_user.user_code}/credits",
        json={"amount": 5, "expires_at": expires},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["amount"] == 5
    assert await ctx.credits.remaining(a_user.user_code) == 5


async def test_granting_to_an_unknown_user_is_404(client, admin_headers) -> None:
    response = await client.post(
        "/api/v1/admin/users/google:ghost/credits",
        json={"amount": 5, "expires_at": to_iso_z(utcnow() + timedelta(days=1))},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_a_past_expiry_is_rejected(client, admin_headers, a_user) -> None:
    response = await client.post(
        f"/api/v1/admin/users/{a_user.user_code}/credits",
        json={"amount": 5, "expires_at": to_iso_z(utcnow() - timedelta(days=1))},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"]["field"] == "expires_at"


# ── 추천 질문 ───────────────────────────────────────────────────────
async def test_creating_a_suggested_question_returns_201(client, admin_headers) -> None:
    response = await client.post(
        "/api/v1/admin/suggested-questions",
        json={"text": "Kafka 최신 글?"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert set(response.json()) == {"id", "text", "sort_order", "is_active"}


async def test_a_duplicate_question_is_409_on_text(client, admin_headers) -> None:
    await client.post(
        "/api/v1/admin/suggested-questions", json={"text": "같은 질문"}, headers=admin_headers
    )

    response = await client.post(
        "/api/v1/admin/suggested-questions",
        json={"text": "  같은   질문 "},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["details"]["field"] == "text"


async def test_deleting_a_question_returns_204(client, admin_headers) -> None:
    created = (
        await client.post(
            "/api/v1/admin/suggested-questions", json={"text": "질문"}, headers=admin_headers
        )
    ).json()

    response = await client.delete(
        f"/api/v1/admin/suggested-questions/{created['id']}", headers=admin_headers
    )

    assert response.status_code == 204


# ── 잡 큐 ───────────────────────────────────────────────────────────
@pytest.fixture
async def dead_job(ctx):
    from techletter.core.jobs.types import JobType

    job = await ctx.queue.enqueue(JobType.SUMMARY_REQUESTED, "post-1", {"post_id": "p"})
    assert job is not None
    await ctx.db["jobs"].update_one(
        {"_id": job.id},
        {"$set": {"status": "dead", "last_error": "boom", "error_kind": "permanent"}},
    )
    return job


async def test_job_shape_hides_the_payload(client, admin_headers, dead_job) -> None:
    """요약 결과 페이로드는 수십 KB다. 목록에 실을 이유가 없다."""
    item = (await client.get("/api/v1/admin/jobs", headers=admin_headers)).json()["items"][0]

    assert "payload" not in item
    assert set(item) == {
        "id",
        "type",
        "key",
        "status",
        "attempt",
        "max_attempt",
        "priority",
        "run_at",
        "last_error",
        "error_kind",
        "trace_id",
        "created_at",
        "updated_at",
        "finished_at",
    }


async def test_jobs_can_be_filtered_by_status(client, admin_headers, dead_job) -> None:
    dead = (await client.get("/api/v1/admin/jobs?status=dead", headers=admin_headers)).json()
    pending = (await client.get("/api/v1/admin/jobs?status=pending", headers=admin_headers)).json()

    assert dead["total"] == 1
    assert pending["total"] == 0


async def test_job_stats_shape(client, admin_headers, dead_job) -> None:
    body = (await client.get("/api/v1/admin/jobs/stats", headers=admin_headers)).json()

    assert set(body) == {"by_status", "by_type", "oldest_pending_at"}
    assert body["by_status"]["dead"] == 1


async def test_retrying_a_dead_job_resets_it(client, admin_headers, dead_job) -> None:
    response = await client.post(f"/api/v1/admin/jobs/{dead_job.id}/retry", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["attempt"] == 0
    assert body["last_error"] is None


async def test_retrying_a_live_job_is_404(client, admin_headers, ctx) -> None:
    from techletter.core.jobs.types import JobType

    job = await ctx.queue.enqueue(JobType.SUMMARY_REQUESTED, "live", {})
    assert job is not None

    response = await client.post(f"/api/v1/admin/jobs/{job.id}/retry", headers=admin_headers)

    assert response.status_code == 404


async def test_bulk_retry_reports_a_count(client, admin_headers, dead_job) -> None:
    response = await client.post(
        "/api/v1/admin/jobs/retry-bulk", json={"limit": 10}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json() == {"retried": 1}


async def test_deleting_a_job_returns_204(client, admin_headers, dead_job) -> None:
    response = await client.delete(f"/api/v1/admin/jobs/{dead_job.id}", headers=admin_headers)

    assert response.status_code == 204


# ── 백필 ────────────────────────────────────────────────────────────
async def test_backfill_status_counts_the_gap(client, admin_headers, seeded) -> None:
    body = (await client.get("/api/v1/admin/backfill/summary", headers=admin_headers)).json()

    assert body["unsummarized"] == 1
    assert body["unembedded"] == 2
    assert body["dead_jobs"] == 0


async def test_backfill_enqueues_and_is_idempotent(client, admin_headers, seeded) -> None:
    first = await client.post(
        "/api/v1/admin/backfill/summary", json={"limit": 10}, headers=admin_headers
    )
    second = await client.post(
        "/api/v1/admin/backfill/summary", json={"limit": 10}, headers=admin_headers
    )

    assert first.status_code == 202
    assert first.json() == {"enqueued": 1}
    # 이미 대기 중인 잡은 중복 억제로 건너뛴다.
    assert second.json() == {"enqueued": 0}


# ── 모델 통계 ───────────────────────────────────────────────────────
async def test_llm_model_stats_shape(client, admin_headers, ctx) -> None:
    from techletter.core.llm.stats import ModelPurpose

    await ctx.model_stats.record("x/model:free", ModelPurpose.CHAT, success=True, latency_ms=120)

    body = (await client.get("/api/v1/admin/llm-models", headers=admin_headers)).json()

    assert set(body) == {"items", "total"}
    item = body["items"][0]
    assert item["model_id"] == "x/model:free"
    assert item["success_rate"] == 1.0
