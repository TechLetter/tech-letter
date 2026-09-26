"""실제 Qdrant·Mongo에 대고 어휘 색인과 하이브리드 검색을 검증한다."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId

from techletter.content.models import AISummary, ListPostsFilter, Post, StatusFlags
from techletter.content.repositories import PostRepository
from techletter.core.db.qdrant import Chunk
from techletter.core.jobs.models import Job
from techletter.core.jobs.types import JobType
from techletter.core.pagination import Page
from techletter.search.handlers import LexicalIndexHandler
from techletter.search.lexical import lexical_point
from techletter.search.service import SearchService
from techletter.settings import SearchSettings

pytestmark = pytest.mark.integration

DIM = 4
BLOG_A = ObjectId()
BLOG_B = ObjectId()


class FakeEmbedder:
    def __init__(self, vector: list[float] | None = None, error: Exception | None = None):
        self.vector = vector or [1.0, 0.0, 0.0, 0.0]
        self.error = error

    async def embed_query(self, text: str) -> list[float]:
        if self.error is not None:
            raise self.error
        return self.vector


def make_post(title: str, *, blog_id=BLOG_A, categories=None, tags=None, summary="", day=1):
    return Post(
        blog_id=blog_id,
        blog_name="Alpha" if blog_id == BLOG_A else "Beta",
        title=title,
        link=f"https://blog.test/{ObjectId()}",
        published_at=datetime(2026, 3, day, tzinfo=UTC),
        status=StatusFlags(ai_summarized=True, embedded=True),
        aisummary=AISummary(categories=categories or ["데이터"], tags=tags or [], summary=summary),
    )


@pytest.fixture
async def corpus(mongo_db, vector_store):
    posts = PostRepository(mongo_db)
    kafka = await posts.insert(
        make_post("카프카 컨슈머 리밸런싱", tags=["Kafka"], summary="컨슈머 그룹 운영기", day=3)
    )
    vllm = await posts.insert(
        make_post(
            "vLLM으로 LLM 서빙하기",
            blog_id=BLOG_B,
            categories=["AI"],
            tags=["vLLM"],
            summary="추론 서버를 옮겼다",
            day=2,
        )
    )
    semantic = await posts.insert(
        make_post("메시지 브로커 장애 회고", summary="브로커 파티션 이야기", day=1)
    )
    unsummarized = make_post("카프카 초안")
    unsummarized.status = StatusFlags()
    draft = await posts.insert(unsummarized)
    assert kafka and vllm and semantic and draft

    await vector_store.upsert_lexical([lexical_point(p) for p in (kafka, vllm, semantic, draft)])
    # 벡터: kafka·semantic은 질의 벡터와 가깝고 vllm은 멀다.
    for post, vector in ((kafka, [1.0, 0.1, 0, 0]), (semantic, [1.0, 0.2, 0, 0])):
        await vector_store.upsert_chunks(
            post_id=str(post.id),
            model_name="fake-embed",
            chunks=[Chunk(chunk_index=0, chunk_text="c", vector=vector)],
            payload={"title": post.title},
        )
    await vector_store.upsert_chunks(
        post_id=str(vllm.id),
        model_name="fake-embed",
        chunks=[Chunk(chunk_index=0, chunk_text="c", vector=[0, 0, 1.0, 0])],
        payload={"title": vllm.title},
    )
    return {"posts": posts, "kafka": kafka, "vllm": vllm, "semantic": semantic, "draft": draft}


def make_service(corpus, vector_store, embedder=None) -> SearchService:
    return SearchService(
        store=vector_store,
        posts=corpus["posts"],
        embedder=embedder or FakeEmbedder(),
        embedding_model="fake-embed",
        settings=SearchSettings(dense_min_score=0.9),
    )


def ids(posts) -> list[str]:
    return [str(post.id) for post in posts]


# ── 색인 ────────────────────────────────────────────────────────────
async def test_lexical_points_are_one_per_post_and_idempotent(corpus, vector_store) -> None:
    await vector_store.upsert_lexical([lexical_point(corpus["kafka"])])

    info = await vector_store._client.count(vector_store.lexical_collection)

    assert info.count == 4


async def test_lexical_search_scores_title_matches(corpus, vector_store) -> None:
    from techletter.search.lexical import query_vector

    hits = await vector_store.search_lexical(query_vector("vllm").indices, limit=5)

    assert [hit.payload["post_id"] for hit in hits] == [str(corpus["vllm"].id)]
    assert hits[0].payload["blog_id"] == str(BLOG_B)
    assert hits[0].payload["categories"] == ["AI"]


async def test_deleting_posts_removes_lexical_points(corpus, vector_store) -> None:
    await vector_store.delete_posts([str(corpus["vllm"].id)])

    info = await vector_store._client.count(vector_store.lexical_collection)

    assert info.count == 3


async def test_the_index_handler_upserts_a_summarized_post(mongo_db, vector_store) -> None:
    posts = PostRepository(mongo_db)
    post = await posts.insert(make_post("쿠버네티스 k8s 운영"))
    assert post is not None

    await LexicalIndexHandler(posts, vector_store)(
        Job(
            type=JobType.LEXICAL_INDEX_REQUESTED,
            key=str(post.id),
            payload={"post_id": str(post.id)},
        )
    )

    items = await make_service({"posts": posts}, vector_store).suggest("k8s")
    assert [item.post_id for item in items] == [str(post.id)]


# ── 자동완성 ────────────────────────────────────────────────────────
async def test_suggest_returns_lexical_matches(corpus, vector_store) -> None:
    items = await make_service(corpus, vector_store).suggest("카프카")

    assert items[0].post_id == str(corpus["kafka"].id)
    assert items[0].title == "카프카 컨슈머 리밸런싱"
    assert items[0].blog_name == "Alpha"
    assert items[0].published_at == "2026-03-03T00:00:00.000Z"
    assert items[0].link == corpus["kafka"].link


async def test_suggest_hides_unsummarized_posts(corpus, vector_store) -> None:
    items = await make_service(corpus, vector_store).suggest("카프카")

    assert str(corpus["draft"].id) not in [item.post_id for item in items]


async def test_suggest_without_an_index_is_empty(mongo_db, vector_store) -> None:
    service = SearchService(
        store=vector_store,
        posts=PostRepository(mongo_db),
        embedder=FakeEmbedder(),
        embedding_model="fake-embed",
        settings=SearchSettings(),
    )

    assert await service.suggest("카프카") == []


# ── 하이브리드 ──────────────────────────────────────────────────────
async def test_hybrid_search_adds_close_dense_hits(corpus, vector_store) -> None:
    found, total = await make_service(corpus, vector_store).search(
        "카프카", ListPostsFilter(summarized=True), Page(1, 20)
    )

    # 어휘로 걸린 kafka가 먼저, 벡터로만 걸린 semantic이 뒤. 요약 안 된 초안과
    # 벡터 점수가 낮은 vllm은 빠진다.
    assert ids(found) == [str(corpus["kafka"].id), str(corpus["semantic"].id)]
    assert total == 2


async def test_hybrid_search_paginates_in_memory(corpus, vector_store) -> None:
    found, total = await make_service(corpus, vector_store).search(
        "카프카", ListPostsFilter(summarized=True), Page(2, 1)
    )

    assert ids(found) == [str(corpus["semantic"].id)]
    assert total == 2


async def test_filters_apply_to_both_sides(corpus, vector_store) -> None:
    service = make_service(corpus, vector_store)

    by_blog, _ = await service.search(
        "카프카", ListPostsFilter(summarized=True, blog_id=str(BLOG_B)), Page(1, 20)
    )
    by_topic, _ = await service.search(
        "vllm 카프카", ListPostsFilter(summarized=True, categories=["AI"]), Page(1, 20)
    )

    assert by_blog == []
    assert ids(by_topic) == [str(corpus["vllm"].id)]


async def test_dense_failure_falls_back_to_lexical(corpus, vector_store) -> None:
    service = make_service(corpus, vector_store, FakeEmbedder(error=RuntimeError("quota")))

    found, total = await service.search("카프카", ListPostsFilter(summarized=True), Page(1, 20))

    assert ids(found) == [str(corpus["kafka"].id)]
    assert total == 1
