"""실제 Mongo에 대고 포스트·블로그 저장소를 검증한다.

집계 파이프라인($unwind/$toLower/$dateTrunc)은 대역으로는 검증되지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from techletter.content.models import AISummary, Blog, ListPostsFilter, Post, StatusFlags
from techletter.content.repositories import BlogRepository, PostRepository
from techletter.core.pagination import Page

if TYPE_CHECKING:  # pragma: no cover
    from bson import ObjectId

pytestmark = pytest.mark.integration


@pytest.fixture
def posts(mongo_db) -> PostRepository:
    return PostRepository(mongo_db)


@pytest.fixture
def blogs(mongo_db) -> BlogRepository:
    return BlogRepository(mongo_db)


def at(day: int) -> datetime:
    return datetime(2025, 3, day, 12, 0, tzinfo=UTC)


async def make_blog(blogs: BlogRepository, name: str, **kwargs) -> Blog:
    slug = name.lower().replace(" ", "-")
    return await blogs.insert(
        Blog(
            name=name,
            url=f"https://{slug}.test",
            rss_url=f"https://{slug}.test/rss",
            **kwargs,
        )
    )


async def make_post(
    posts: PostRepository,
    blog: Blog,
    title: str,
    *,
    published: datetime | None = None,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
    summarized: bool = True,
) -> Post:
    saved = await posts.insert(
        Post(
            blog_id=blog.id,
            blog_name=blog.name,
            title=title,
            link=f"https://{blog.name.lower()}.test/{title.lower().replace(' ', '-')}",
            published_at=published or at(1),
            plain_text=f"body of {title}",
            status=StatusFlags(ai_summarized=summarized),
            aisummary=AISummary(categories=categories or [], tags=tags or []),
        )
    )
    assert saved is not None
    return saved


# ── 목록 ────────────────────────────────────────────────────────────
async def test_list_is_newest_first_and_hides_the_body(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    await make_post(posts, blog, "old", published=at(1))
    await make_post(posts, blog, "new", published=at(9))

    found, total = await posts.list_posts(ListPostsFilter(), Page(1, 10))

    assert [p.title for p in found] == ["new", "old"]
    assert total == 2
    assert found[0].plain_text is None  # 목록에 본문을 싣지 않는다


async def test_list_can_include_the_body_when_asked(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    await make_post(posts, blog, "one")

    found, _ = await posts.list_posts(ListPostsFilter(), Page(1, 10), with_body=True)

    assert found[0].plain_text == "body of one"


async def test_pagination_slices_without_changing_the_total(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    for day in range(1, 6):
        await make_post(posts, blog, f"post {day}", published=at(day))

    page2, total = await posts.list_posts(ListPostsFilter(), Page(2, 2))

    assert total == 5
    assert [p.title for p in page2] == ["post 3", "post 2"]


async def test_categories_and_tags_are_a_union(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    await make_post(posts, blog, "a", categories=["Backend"], tags=["Go"])
    await make_post(posts, blog, "b", categories=["AI"], tags=["Kafka"])
    await make_post(posts, blog, "c", categories=["Infra"], tags=["Nix"])

    found, total = await posts.list_posts(
        ListPostsFilter(categories=["Backend"], tags=["Kafka"]), Page(1, 10)
    )

    assert total == 2
    assert {p.title for p in found} == {"a", "b"}


async def test_tag_match_ignores_case_but_not_partial_words(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    await make_post(posts, blog, "exact", tags=["Kafka"])
    await make_post(posts, blog, "partial", tags=["Kafka Connect"])

    found, _ = await posts.list_posts(ListPostsFilter(tags=["kafka"]), Page(1, 10))

    assert [p.title for p in found] == ["exact"]


async def test_unsummarized_filter_matches_documents_without_the_field(
    posts, blogs, mongo_db
) -> None:
    blog = await make_blog(blogs, "Alpha")
    await make_post(posts, blog, "done", summarized=True)
    await make_post(posts, blog, "pending", summarized=False)
    # 필드가 통째로 없는 오래된 문서
    await mongo_db["posts"].insert_one(
        {"title": "legacy", "link": "https://legacy.test/1", "published_at": at(1), "status": {}}
    )

    found, total = await posts.list_posts(ListPostsFilter(summarized=False), Page(1, 10))

    assert total == 2
    assert {p.title for p in found} == {"pending", "legacy"}


async def test_search_matches_title_or_blog_name(posts, blogs) -> None:
    alpha = await make_blog(blogs, "Kafka Weekly")
    beta = await make_blog(blogs, "Beta")
    await make_post(posts, alpha, "unrelated")
    await make_post(posts, beta, "Kafka rebalancing")
    await make_post(posts, beta, "nothing here")

    found, total = await posts.list_posts(ListPostsFilter(search="kafka"), Page(1, 10))

    assert total == 2
    assert {p.title for p in found} == {"unrelated", "Kafka rebalancing"}


async def test_published_range_is_inclusive_on_both_ends(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    for day in (1, 5, 9):
        await make_post(posts, blog, f"day {day}", published=at(day))

    _, total = await posts.list_posts(
        ListPostsFilter(published_from=at(1), published_to=at(5)), Page(1, 10)
    )

    assert total == 2


# ── 단건·벌크 ───────────────────────────────────────────────────────
async def test_get_returns_utc_aware_datetimes(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    saved = await make_post(posts, blog, "one")

    found = await posts.get(str(saved.id))

    assert found is not None
    assert found.published_at.tzinfo is not None
    assert found.published_at == at(1)


async def test_get_with_a_malformed_id_returns_none(posts) -> None:
    assert await posts.get("not-an-id") is None


async def test_get_many_ignores_unknown_ids(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    one = await make_post(posts, blog, "one")

    found = await posts.get_many([str(one.id), "507f1f77bcf86cd799439011", "bad"])

    assert list(found) == [str(one.id)]


async def test_plain_texts_are_fetched_in_one_query(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    one = await make_post(posts, blog, "one")
    two = await make_post(posts, blog, "two")

    bodies = await posts.get_plain_texts([str(one.id), str(two.id)])

    assert bodies == {str(one.id): "body of one", str(two.id): "body of two"}


async def test_duplicate_link_is_rejected_by_the_unique_index(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    await make_post(posts, blog, "one")

    again = await posts.insert(
        Post(
            blog_id=blog.id,
            blog_name=blog.name,
            title="dup",
            link=(await posts.list_posts(ListPostsFilter(), Page(1, 1)))[0][0].link,
        )
    )

    assert again is None


async def test_existing_link_keys_matches_by_link_or_link_key(posts, blogs) -> None:
    """원문 링크로 와도, 정규화된 link_key로 와도 같은 문서를 잡아야 한다 —
    link_key 도입 전 문서와 전환 중인 문서가 섞여 있기 때문이다."""
    blog = await make_blog(blogs, "Alpha")
    saved = await make_post(posts, blog, "one")

    by_link = await posts.existing_link_keys([saved.link], [])
    assert by_link == {saved.link, saved.link_key}

    by_key = await posts.existing_link_keys(["https://alpha.test/never-seen"], [saved.link_key])
    assert by_key == {saved.link, saved.link_key}

    assert await posts.existing_link_keys(["https://alpha.test/nope"], ["nope-key"]) == set()
    assert await posts.existing_link_keys([], []) == set()


async def test_view_count_increments(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    saved = await make_post(posts, blog, "one")

    assert await posts.increment_view(str(saved.id)) is True
    assert await posts.increment_view(str(saved.id)) is True

    found = await posts.get(str(saved.id))
    assert found is not None
    assert found.view_count == 2


async def test_apply_summary_updates_nested_fields_without_clobbering_siblings(
    posts, blogs
) -> None:
    blog = await make_blog(blogs, "Alpha")
    saved = await make_post(posts, blog, "one", summarized=False)
    await posts.apply_summary(str(saved.id), {"status.embedded": True})

    await posts.apply_summary(str(saved.id), {"status.ai_summarized": True})

    found = await posts.get(str(saved.id))
    assert found is not None
    assert found.status.ai_summarized is True
    assert found.status.embedded is True  # 앞선 플래그가 살아 있다


# ── 집계 ────────────────────────────────────────────────────────────
async def test_facet_counts_group_case_insensitively_and_keep_a_real_spelling(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    await make_post(posts, blog, "a", tags=["Kafka"])
    await make_post(posts, blog, "b", tags=["kafka"])
    await make_post(posts, blog, "c", tags=["KAFKA"])

    counts = await posts.tag_counts(None, [])

    assert list(counts.values()) == [3]
    assert next(iter(counts)).lower() == "kafka"


async def test_facet_counts_scope_to_a_blog(posts, blogs) -> None:
    alpha = await make_blog(blogs, "Alpha")
    beta = await make_blog(blogs, "Beta")
    await make_post(posts, alpha, "a", tags=["Kafka"])
    await make_post(posts, beta, "b", tags=["Kafka"])

    assert await posts.tag_counts(str(alpha.id), []) == {"Kafka": 1}
    assert await posts.tag_counts(None, []) == {"Kafka": 2}


async def test_blog_counts_report_id_name_and_total(posts, blogs) -> None:
    alpha = await make_blog(blogs, "Alpha")
    await make_post(posts, alpha, "a", categories=["AI"])
    await make_post(posts, alpha, "b", categories=["AI"])

    rows = await posts.blog_counts(["ai"], [])

    assert rows == [(str(alpha.id), "Alpha", 2)]


async def test_topic_activity_counts_posts_and_distinct_blogs(posts, blogs) -> None:
    alpha = await make_blog(blogs, "Alpha")
    beta = await make_blog(blogs, "Beta")
    old = await make_post(posts, alpha, "a", categories=["RAG·검색"], published=at(1))
    new = await make_post(posts, alpha, "b", categories=["RAG·검색", "모바일"], published=at(3))
    other = await make_post(posts, beta, "c", categories=["RAG·검색"], published=at(2))
    await make_post(
        posts, beta, "draft", categories=["RAG·검색"], published=at(2), summarized=False
    )
    await make_post(posts, beta, "edge", categories=["RAG·검색"], published=at(9))

    rows = {row.topic: row for row in await posts.topic_activity(at(1), at(9))}

    rag = rows["RAG·검색"]
    assert (rag.post_count, rag.blog_count) == (3, 2)  # 요약 전 글, 상한 경계는 뺀다
    assert rag.recent == [(str(new.id), "Alpha"), (str(other.id), "Beta"), (str(old.id), "Alpha")]
    assert (rows["모바일"].post_count, rows["모바일"].blog_count) == (1, 1)


async def test_activity_totals_count_summarized_posts_and_blogs(posts, blogs) -> None:
    alpha = await make_blog(blogs, "Alpha")
    beta = await make_blog(blogs, "Beta")
    await make_post(posts, alpha, "a", published=at(2))
    await make_post(posts, alpha, "b", published=at(3))
    await make_post(posts, beta, "c", published=at(3), summarized=False)

    assert await posts.activity_totals(at(1), at(9)) == (2, 1)


# ── 블로그 ──────────────────────────────────────────────────────────
async def test_list_blogs_hides_inactive_by_default(blogs) -> None:
    await make_blog(blogs, "Alpha")
    await make_blog(blogs, "Beta", is_active=False)

    active, total = await blogs.list_blogs(Page(1, 10))
    inactive, inactive_total = await blogs.list_blogs(Page(1, 10), active=False)
    every, every_total = await blogs.list_blogs(Page(1, 10), active=None)

    assert total == 1 and [b.name for b in active] == ["Alpha"]
    assert inactive_total == 1 and [b.name for b in inactive] == ["Beta"]
    assert every_total == 2 and len(every) == 2


async def test_active_list_treats_a_missing_flag_as_active(blogs, mongo_db) -> None:
    await mongo_db["blogs"].insert_one(
        {"name": "Legacy", "url": "https://legacy.test", "rss_url": "https://legacy.test/rss"}
    )

    assert [b.name for b in await blogs.list_active()] == ["Legacy"]


async def test_fetch_success_clears_the_error_and_the_failure_counter(blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    assert blog.id is not None
    await blogs.record_fetch_result(blog.id, "boom")

    assert await blogs.record_fetch_result(blog.id, None) == 0

    found = await blogs.get(str(blog.id))
    assert found is not None
    assert found.last_fetch_error is None
    assert found.consecutive_failures == 0
    assert found.last_fetched_at is not None


async def test_consecutive_failures_accumulate(blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    assert blog.id is not None

    counts = [await blogs.record_fetch_result(blog.id, "boom") for _ in range(3)]

    assert counts == [1, 2, 3]


async def test_fetch_error_is_truncated(blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    assert blog.id is not None

    await blogs.record_fetch_result(blog.id, "x" * 5000)

    found = await blogs.get(str(blog.id))
    assert found is not None
    assert found.last_fetch_error is not None
    assert len(found.last_fetch_error) == 200


async def test_duplicate_rss_url_is_rejected(blogs) -> None:
    from pymongo.errors import DuplicateKeyError

    await make_blog(blogs, "Alpha")
    with pytest.raises(DuplicateKeyError):
        await blogs.insert(
            Blog(name="Copy", url="https://other.test", rss_url="https://alpha.test/rss")
        )


async def test_find_conflict_matches_a_trailing_slash_variant(blogs) -> None:
    await make_blog(blogs, "Alpha")

    conflict = await blogs.find_conflict(
        url="https://other.test", rss_url="https://alpha.test/rss", exclude_id=None
    )

    assert conflict == "rss_url"


async def test_find_conflict_excludes_the_blog_being_edited(blogs) -> None:
    blog = await make_blog(blogs, "Alpha")

    conflict = await blogs.find_conflict(url=blog.url, rss_url=blog.rss_url, exclude_id=blog.id)

    assert conflict is None


async def test_delete_by_blog_removes_only_that_blogs_posts(posts, blogs) -> None:
    alpha = await make_blog(blogs, "Alpha")
    beta = await make_blog(blogs, "Beta")
    await make_post(posts, alpha, "a")
    await make_post(posts, alpha, "b")
    await make_post(posts, beta, "c")
    assert alpha.id is not None

    ids: list[str] = await posts.ids_by_blog(alpha.id)
    deleted = await posts.delete_by_blog(alpha.id)

    assert len(ids) == 2
    assert deleted == 2
    _, total = await posts.list_posts(ListPostsFilter(), Page(1, 10))
    assert total == 1


async def test_count_by_blog_reports_zero_for_empty_blogs(posts, blogs) -> None:
    alpha = await make_blog(blogs, "Alpha")
    empty = await make_blog(blogs, "Empty")
    await make_post(posts, alpha, "a")
    ids: list[ObjectId] = [b.id for b in (alpha, empty) if b.id is not None]

    counts = await posts.count_by_blog(ids)

    assert counts == {str(alpha.id): 1, str(empty.id): 0}


async def test_backfill_queries_find_the_right_posts(posts, blogs) -> None:
    blog = await make_blog(blogs, "Alpha")
    await make_post(posts, blog, "todo", summarized=False, published=at(1))
    done = await make_post(posts, blog, "done", summarized=True, published=at(2))
    await posts.apply_summary(str(done.id), {"status.embedded": True})
    await make_post(posts, blog, "half", summarized=True, published=at(3))

    unsummarized = await posts.find_unsummarized(10)
    unembedded = await posts.find_summarized_not_embedded(10)

    assert [p.title for p in unsummarized] == ["todo"]
    assert [p.title for p in unembedded] == ["half"]


async def test_indexes_use_the_existing_names(mongo_db) -> None:
    """이름이 다르면 같은 키에 중복 인덱스가 생긴다."""
    names = {idx["name"] async for idx in await mongo_db["posts"].list_indexes()}

    assert {
        "idx_published_at_desc",
        "idx_categories",
        "idx_tags",
        "uniq_link",
        "idx_published_at_id_desc",
        "idx_tags_published_at",
        "idx_categories_published_at",
    } <= names


# ── 주제 재분류 ─────────────────────────────────────────────────────
async def test_posts_with_categories_outside_the_topics_need_reclassifying(posts, blogs) -> None:
    """목록 밖의 값이 하나라도 있으면 대상이다. 그래서 버전 필드 없이 이어서 돌릴 수 있다."""
    blog = await make_blog(blogs, "Alpha")
    names = ("RAG·검색", "모바일")
    await make_post(posts, blog, "done", categories=["RAG·검색", "모바일"], published=at(1))
    mixed = await make_post(posts, blog, "mixed", categories=["RAG·검색", "AI"], published=at(2))
    old = await make_post(posts, blog, "old", categories=["Backend"], published=at(3))
    empty = await make_post(posts, blog, "empty", categories=[], published=at(4))
    await make_post(posts, blog, "pending", categories=["AI"], summarized=False)

    found = await posts.find_needing_topics(names, 10)

    assert [p.id for p in found] == [empty.id, old.id, mixed.id]  # 최근 글부터
    assert all(p.plain_text is None for p in found)  # 본문은 싣지 않는다

    assert await posts.set_categories(str(old.id), ["모바일"])
    assert old.id not in {p.id for p in await posts.find_needing_topics(names, 10)}


async def test_relinking_onto_another_posts_link_is_refused(posts, blogs) -> None:
    """새 주소가 이미 다른 글의 것이면 옮기지 않는다 — 고유 키가 깨진다."""
    blog = await make_blog(blogs, "Alpha")
    a = await make_post(posts, blog, "a")
    b = await make_post(posts, blog, "b")

    assert not await posts.relink(str(a.id), b.link, b.link_key or b.link)
    assert await posts.relink(str(a.id), "https://alpha.test/a-moved", "https://alpha.test/a-moved")
    assert [p.id for p in await posts.find_by_titles(blog.id, ["a"])] == [a.id]
