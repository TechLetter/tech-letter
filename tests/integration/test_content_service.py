"""content 서비스와 요약 완료 핸들러."""

from __future__ import annotations

import pytest

from techletter.content.handlers import (
    EmbeddingCompletedHandler,
    SummaryCompletedHandler,
    record_summary_failure,
)
from techletter.content.jobs import EmbeddingCompletedPayload, SummaryCompletedPayload
from techletter.content.models import Blog, ListPostsFilter
from techletter.content.repositories import BlogRepository, PostRepository
from techletter.content.service import BlogService, PostService
from techletter.core.errors import (
    InvalidRequestError,
    PermanentError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from techletter.core.jobs.models import Job
from techletter.core.jobs.types import JobType
from techletter.core.pagination import Page

pytestmark = pytest.mark.integration


@pytest.fixture
def posts(mongo_db) -> PostRepository:
    return PostRepository(mongo_db)


@pytest.fixture
def blogs(mongo_db) -> BlogRepository:
    return BlogRepository(mongo_db)


@pytest.fixture
def post_service(posts, blogs, queue) -> PostService:
    return PostService(posts, blogs, queue)


@pytest.fixture
def blog_service(blogs, posts, queue) -> BlogService:
    return BlogService(blogs, posts, queue)


@pytest.fixture
async def blog(blog_service) -> Blog:
    return await blog_service.create(
        name="Alpha", url="https://alpha.test/", rss_url="https://alpha.test/rss/"
    )


# ── 블로그 ──────────────────────────────────────────────────────────
async def test_create_strips_the_trailing_slash(blog) -> None:
    assert blog.url == "https://alpha.test"
    assert blog.rss_url == "https://alpha.test/rss"


async def test_duplicate_rss_url_is_a_conflict(blog_service, blog) -> None:
    with pytest.raises(ResourceConflictError) as excinfo:
        await blog_service.create(
            name="Copy", url="https://other.test", rss_url="https://alpha.test/rss"
        )

    assert excinfo.value.status == 409
    assert excinfo.value.details["field"] == "rss_url"


async def test_unknown_blog_type_is_a_client_error(blog_service) -> None:
    with pytest.raises(InvalidRequestError):
        await blog_service.create(
            name="X", url="https://x.test", rss_url="https://x.test/rss", blog_type="podcast"
        )


async def test_update_is_partial_and_keeps_untouched_fields(blog_service, blogs, blog) -> None:
    assert blog.id is not None
    await blogs.record_fetch_result(blog.id, None)

    updated = await blog_service.update(str(blog.id), {"name": "Alpha Renamed"})

    assert updated.name == "Alpha Renamed"
    assert updated.rss_url == "https://alpha.test/rss"
    # 전체 교체였다면 여기서 사라진다.
    assert updated.last_fetched_at is not None


async def test_update_can_keep_its_own_urls(blog_service, blog) -> None:
    updated = await blog_service.update(str(blog.id), {"url": blog.url, "name": "Same"})

    assert updated.name == "Same"


async def test_update_rejects_another_blogs_url(blog_service, blog) -> None:
    other = await blog_service.create(
        name="Beta", url="https://beta.test", rss_url="https://beta.test/rss"
    )

    with pytest.raises(ResourceConflictError):
        await blog_service.update(str(other.id), {"rss_url": "https://alpha.test/rss"})


async def test_reactivating_clears_the_failure_counter(blog_service, blogs, blog) -> None:
    assert blog.id is not None
    for _ in range(5):
        await blogs.record_fetch_result(blog.id, "boom")
    await blogs.deactivate(blog.id, "auto-disabled")

    updated = await blog_service.update(str(blog.id), {"is_active": True})

    assert updated.is_active is True
    assert updated.consecutive_failures == 0
    assert updated.last_fetch_error is None


async def test_list_attaches_post_counts(blog_service, post_service, blog) -> None:
    await post_service.create(title="one", link="https://alpha.test/1", blog_id=str(blog.id))
    await blog_service.create(name="Empty", url="https://e.test", rss_url="https://e.test/rss")

    rows, total = await blog_service.list(Page(1, 10))

    assert total == 2
    assert {row.blog.name: row.post_count for row in rows} == {"Alpha": 1, "Empty": 0}


async def test_delete_without_posts_leaves_them_orphaned(
    blog_service, post_service, posts, blog
) -> None:
    await post_service.create(title="one", link="https://alpha.test/1", blog_id=str(blog.id))

    deleted = await blog_service.delete(str(blog.id))

    assert deleted == 0
    _, total = await posts.list_posts(ListPostsFilter(), Page(1, 10))
    assert total == 1


async def test_delete_with_posts_queues_one_vector_cleanup_job(
    blog_service, post_service, mongo_db, blog
) -> None:
    for n in range(3):
        await post_service.create(
            title=f"p{n}", link=f"https://alpha.test/{n}", blog_id=str(blog.id)
        )

    deleted = await blog_service.delete(str(blog.id), delete_posts=True)

    assert deleted == 3
    jobs = [
        job
        async for job in mongo_db["jobs"].find({"type": JobType.EMBEDDING_DELETE_REQUESTED.value})
    ]
    # 포스트마다 잡을 만들지 않는다. 한 건에 묶는다.
    assert len(jobs) == 1
    assert len(jobs[0]["payload"]["post_ids"]) == 3


async def test_deleting_an_unknown_blog_is_not_found(blog_service) -> None:
    with pytest.raises(ResourceNotFoundError):
        await blog_service.delete("507f1f77bcf86cd799439011")


# ── 포스트 ──────────────────────────────────────────────────────────
async def test_manual_create_queues_a_summary(post_service, mongo_db, blog) -> None:
    post = await post_service.create(
        title="manual", link="https://alpha.test/manual", blog_id=str(blog.id)
    )

    assert post.blog_name == "Alpha"
    assert post.status.ai_summarized is False
    assert await mongo_db["jobs"].count_documents({"key": str(post.id)}) == 1


async def test_manual_create_rejects_a_duplicate_link(post_service, blog) -> None:
    await post_service.create(title="a", link="https://alpha.test/x", blog_id=str(blog.id))

    with pytest.raises(ResourceConflictError):
        await post_service.create(title="b", link="https://alpha.test/x", blog_id=str(blog.id))


async def test_manual_create_needs_an_existing_blog(post_service) -> None:
    with pytest.raises(ResourceNotFoundError):
        await post_service.create(
            title="x", link="https://x.test/1", blog_id="507f1f77bcf86cd799439011"
        )


async def test_get_many_preserves_the_requested_order(post_service, blog) -> None:
    one = await post_service.create(title="1", link="https://a.test/1", blog_id=str(blog.id))
    two = await post_service.create(title="2", link="https://a.test/2", blog_id=str(blog.id))

    found = await post_service.get_many([str(two.id), "507f1f77bcf86cd799439011", str(one.id)])

    assert [p.title for p in found] == ["2", "1"]


async def test_delete_queues_vector_cleanup(post_service, mongo_db, blog) -> None:
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))

    await post_service.delete(str(post.id))

    job = await mongo_db["jobs"].find_one({"type": JobType.EMBEDDING_DELETE_REQUESTED.value})
    assert job is not None
    assert job["payload"]["post_ids"] == [str(post.id)]


async def test_retry_summary_requires_the_post_to_exist(post_service) -> None:
    with pytest.raises(ResourceNotFoundError):
        await post_service.retry_summary("507f1f77bcf86cd799439011")


async def test_retry_is_deduped_while_one_is_pending(post_service, mongo_db, blog) -> None:
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))

    await post_service.retry_summary(str(post.id))
    await post_service.retry_summary(str(post.id))

    assert await mongo_db["jobs"].count_documents({"key": str(post.id)}) == 1


# ── 요약 완료 핸들러 ────────────────────────────────────────────────
def completed_job(payload: SummaryCompletedPayload) -> Job:
    return Job(type=JobType.SUMMARY_COMPLETED, key=payload.post_id, payload=payload.to_dict())


async def test_summary_is_written_and_embedding_is_queued(
    post_service, posts, queue, mongo_db, blog
) -> None:
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))
    handler = SummaryCompletedHandler(posts, queue)

    await handler(
        completed_job(
            SummaryCompletedPayload(
                post_id=str(post.id),
                summary="요약문",
                categories=["Backend"],
                tags=["Kafka"],
                model_name="nvidia/nemotron",
                plain_text="본문",
                thumbnail_url="https://alpha.test/thumb.png",
            )
        )
    )

    found = await posts.get(str(post.id))
    assert found is not None
    assert found.status.ai_summarized is True
    assert found.aisummary is not None
    assert found.aisummary.summary == "요약문"
    assert found.aisummary.tags == ["Kafka"]
    assert found.aisummary.generated_at is not None
    assert found.thumbnail_url == "https://alpha.test/thumb.png"
    assert await posts.get_plain_text(str(post.id)) == "본문"
    assert await mongo_db["jobs"].count_documents({"type": JobType.EMBEDDING_REQUESTED.value}) == 1


async def test_applying_a_summary_keeps_the_embedded_flag(post_service, posts, queue, blog) -> None:
    """요약과 임베딩 워커가 같은 문서를 건드린다. status 를 통째로 덮으면 안 된다."""
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))
    await posts.apply_summary(str(post.id), {"status.embedded": True})

    await SummaryCompletedHandler(posts, queue)(
        completed_job(SummaryCompletedPayload(post_id=str(post.id), summary="s"))
    )

    found = await posts.get(str(post.id))
    assert found is not None
    assert found.status.embedded is True


async def test_an_empty_body_does_not_erase_the_stored_one(
    post_service, posts, queue, blog
) -> None:
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))
    handler = SummaryCompletedHandler(posts, queue)
    await handler(
        completed_job(SummaryCompletedPayload(post_id=str(post.id), summary="s", plain_text="본문"))
    )

    await handler(completed_job(SummaryCompletedPayload(post_id=str(post.id), summary="s2")))

    assert await posts.get_plain_text(str(post.id)) == "본문"


async def test_a_summary_for_a_deleted_post_is_permanent(posts, queue) -> None:
    with pytest.raises(PermanentError) as excinfo:
        await SummaryCompletedHandler(posts, queue)(
            completed_job(SummaryCompletedPayload(post_id="507f1f77bcf86cd799439011", summary="s"))
        )

    assert excinfo.value.reason == "post_deleted"


async def test_a_payload_without_a_post_id_is_permanent(posts, queue) -> None:
    with pytest.raises(PermanentError) as excinfo:
        await SummaryCompletedHandler(posts, queue)(
            completed_job(SummaryCompletedPayload(post_id="", summary="s"))
        )

    assert excinfo.value.reason == "bad_payload"


async def test_replaying_the_same_summary_is_idempotent(
    post_service, posts, queue, mongo_db, blog
) -> None:
    """잡은 최소 1회 전달이다. 같은 결과가 두 번 와도 상태와 큐가 같아야 한다."""
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))
    handler = SummaryCompletedHandler(posts, queue)
    payload = SummaryCompletedPayload(
        post_id=str(post.id), summary="s", tags=["Go"], plain_text="본문"
    )

    await handler(completed_job(payload))
    first = await posts.get(str(post.id))
    await handler(completed_job(payload))
    second = await posts.get(str(post.id))

    assert first is not None and second is not None
    assert first.status == second.status
    assert first.aisummary is not None and second.aisummary is not None
    assert first.aisummary.tags == second.aisummary.tags
    # 임베딩 잡은 한 번만 남는다(대기 중이면 중복 억제).
    assert await mongo_db["jobs"].count_documents({"type": JobType.EMBEDDING_REQUESTED.value}) == 1


def embedding_job(payload: EmbeddingCompletedPayload) -> Job:
    return Job(type=JobType.EMBEDDING_COMPLETED, key=payload.post_id, payload=payload.to_dict())


async def test_embedding_metadata_is_recorded(post_service, posts, blog) -> None:
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))

    await EmbeddingCompletedHandler(posts)(
        embedding_job(
            EmbeddingCompletedPayload(
                post_id=str(post.id),
                model_name="gemini-embedding-001",
                collection_name="tech_letter_posts__gemini-embedding-001__3072",
                vector_dimension=3072,
                chunk_count=17,
            )
        )
    )

    found = await posts.get(str(post.id))
    assert found is not None
    assert found.status.embedded is True
    assert found.embedding is not None
    assert found.embedding.chunk_count == 17
    assert found.embedding.embedded_at is not None


async def test_embedding_result_does_not_clear_the_summary_flag(
    post_service, posts, queue, blog
) -> None:
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))
    await SummaryCompletedHandler(posts, queue)(
        completed_job(SummaryCompletedPayload(post_id=str(post.id), summary="s"))
    )

    await EmbeddingCompletedHandler(posts)(
        embedding_job(
            EmbeddingCompletedPayload(
                post_id=str(post.id),
                model_name="m",
                collection_name="c",
                vector_dimension=1,
                chunk_count=1,
            )
        )
    )

    found = await posts.get(str(post.id))
    assert found is not None
    assert found.status.ai_summarized is True
    assert found.status.embedded is True


async def test_permanent_summary_failure_leaves_a_reason(post_service, posts, blog) -> None:
    """요약 안 된 포스트가 왜 그런지 어드민에서 보여야 한다."""
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))

    await record_summary_failure(posts, str(post.id), "render failed: HTTP 404")

    found = await posts.get(str(post.id))
    assert found is not None
    assert found.status.ai_summarized is False
    assert found.status.failed_reason == "render failed: HTTP 404"


async def test_a_retried_summary_clears_the_previous_failure(
    post_service, posts, queue, blog
) -> None:
    post = await post_service.create(title="x", link="https://alpha.test/x", blog_id=str(blog.id))
    await record_summary_failure(posts, str(post.id), "boom")

    await SummaryCompletedHandler(posts, queue)(
        completed_job(SummaryCompletedPayload(post_id=str(post.id), summary="s"))
    )

    found = await posts.get(str(post.id))
    assert found is not None
    assert found.status.failed_reason is None
