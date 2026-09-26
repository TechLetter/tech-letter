"""검색 계약 — 자동완성과 `/posts?q=`."""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.contract]

TEST_QDRANT_HOST = os.environ.get("TEST_QDRANT_HOST", "localhost")
TEST_QDRANT_PORT = int(os.environ.get("TEST_QDRANT_PORT", "6334"))
COLLECTION_BASE = "techletter_contract"

SUGGESTION_KEYS = {"id", "title", "blog_id", "blog_name", "published_at", "link"}


class FakeEmbedder:
    """벡터 컬렉션이 없는 환경이라 벡터 쪽은 빈 결과가 된다(어휘만으로 답한다)."""

    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * 4


@pytest.fixture
async def search_index(ctx, seeded):
    from qdrant_client import AsyncQdrantClient

    from techletter.core.db.qdrant import VectorStore
    from techletter.search.lexical import lexical_point
    from techletter.search.service import SearchService
    from techletter.settings import QdrantSettings

    probe = AsyncQdrantClient(host=TEST_QDRANT_HOST, port=TEST_QDRANT_PORT, timeout=2)
    try:
        await probe.get_collections()
    except Exception as exc:
        await probe.close()
        pytest.skip(f"테스트 Qdrant에 접속할 수 없다: {exc}")

    store = VectorStore(
        QdrantSettings(
            QDRANT_HOST=TEST_QDRANT_HOST,
            QDRANT_PORT=TEST_QDRANT_PORT,
            QDRANT_COLLECTION_NAME=COLLECTION_BASE,
        )
    )
    await store.upsert_lexical([lexical_point(post) for post in seeded["posts"]])
    ctx._search = SearchService(
        store=store,
        posts=ctx.posts,
        embedder=FakeEmbedder(),
        embedding_model="fake-embed",
        settings=ctx.settings.search,
    )
    yield seeded

    for collection in (await probe.get_collections()).collections:
        if collection.name.startswith(COLLECTION_BASE):
            await probe.delete_collection(collection.name)
    await probe.close()
    await store.close()


# ── 자동완성 ────────────────────────────────────────────────────────
async def test_suggest_uses_the_short_envelope(client, search_index) -> None:
    body = (await client.get("/api/v1/search/suggest", params={"q": "Go"})).json()

    assert set(body) == {"items", "total"}
    assert body["total"] == len(body["items"]) == 1
    item = body["items"][0]
    assert set(item) == SUGGESTION_KEYS
    assert item["id"] == str(search_index["posts"][0].id)
    assert item["title"] == "제목 0"
    assert item["blog_id"] == str(search_index["blog"].id)
    assert item["blog_name"] == "Alpha"
    assert item["published_at"] == "2025-03-01T00:00:00.000Z"
    assert item["link"] == "https://alpha.test/0"


async def test_suggest_returns_at_most_five(client, search_index) -> None:
    body = (await client.get("/api/v1/search/suggest", params={"q": "제목"})).json()

    assert 1 <= body["total"] <= 5


@pytest.mark.parametrize("q", ["", "a", None])
async def test_a_too_short_suggest_query_is_empty(client, search_index, q) -> None:
    params = {} if q is None else {"q": q}
    body = (await client.get("/api/v1/search/suggest", params=params)).json()

    assert body == {"items": [], "total": 0}


# ── /posts?q= ───────────────────────────────────────────────────────
async def test_searching_posts_keeps_the_paged_envelope(client, search_index) -> None:
    from tests.contract.test_public_contract import PAGED_KEYS, POST_KEYS

    body = (await client.get("/api/v1/posts", params={"q": "Go"})).json()

    assert set(body) == PAGED_KEYS
    assert body["total"] == 1
    assert body["total_pages"] == 1
    assert set(body["items"][0]) == POST_KEYS
    assert body["items"][0]["id"] == str(search_index["posts"][0].id)


async def test_search_ignores_sort_and_pages_in_memory(client, search_index) -> None:
    body = (
        await client.get("/api/v1/posts", params={"q": "제목", "sort": "views", "page_size": 2})
    ).json()

    assert body["total"] == 3
    assert body["total_pages"] == 2
    assert len(body["items"]) == 2


async def test_search_still_applies_filters(client, search_index) -> None:
    other_blog = "0" * 24

    body = (await client.get("/api/v1/posts", params={"q": "제목", "blog_id": other_blog})).json()
    by_tag = (await client.get("/api/v1/posts", params={"q": "제목", "tags": "Go"})).json()

    assert body["total"] == 0
    assert [item["id"] for item in by_tag["items"]] == [str(search_index["posts"][0].id)]


async def test_a_one_letter_query_lists_posts_as_usual(client, search_index) -> None:
    plain = (await client.get("/api/v1/posts")).json()
    short = (await client.get("/api/v1/posts", params={"q": "제"})).json()

    assert short == plain
