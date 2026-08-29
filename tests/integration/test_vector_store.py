"""실제 Qdrant에 대고 벡터 저장·검색·삭제를 검증한다."""

from __future__ import annotations

import pytest

from techletter.core.db.qdrant import Chunk

pytestmark = pytest.mark.integration

DIM = 8


def vec(seed: float) -> list[float]:
    return [seed] * DIM


def chunks(count: int, seed: float = 0.5) -> list[Chunk]:
    return [
        Chunk(chunk_index=index, chunk_text=f"조각 {index}", vector=vec(seed + index * 0.01))
        for index in range(count)
    ]


async def test_upsert_creates_the_collection_and_reports_it(vector_store) -> None:
    result = await vector_store.upsert_chunks(
        post_id="p1", model_name="test-embed", chunks=chunks(3), payload={"title": "글"}
    )

    assert result.chunk_count == 3
    assert result.vector_dimension == DIM
    assert result.collection_name == "techletter_itest__test-embed__8"


async def test_no_chunks_is_a_no_op(vector_store) -> None:
    result = await vector_store.upsert_chunks(
        post_id="p1", model_name="test-embed", chunks=[], payload={}
    )

    assert result.chunk_count == 0


async def test_search_returns_payloads(vector_store) -> None:
    await vector_store.upsert_chunks(
        post_id="p1",
        model_name="test-embed",
        chunks=chunks(2),
        payload={"title": "Kafka 글", "link": "https://b.test/1"},
    )

    hits = await vector_store.search(vec(0.5), "test-embed", limit=5, score_threshold=0.0)

    assert hits
    assert hits[0].payload["post_id"] == "p1"
    assert hits[0].payload["title"] == "Kafka 글"
    assert "chunk_text" in hits[0].payload


async def test_reembedding_replaces_instead_of_duplicating(vector_store) -> None:
    """포인트 id가 결정적이라 같은 청크는 덮어써진다."""
    for _ in range(3):
        await vector_store.upsert_chunks(
            post_id="p1", model_name="test-embed", chunks=chunks(2), payload={}
        )

    hits = await vector_store.search(vec(0.5), "test-embed", limit=50, score_threshold=0.0)

    assert len(hits) == 2


async def test_a_missing_collection_degrades_to_empty(vector_store) -> None:
    """벡터 검색이 안 되더라도 챗봇은 "못 찾았다"로 답해야 한다."""
    assert await vector_store.search(vec(0.5), "never-used-model") == []


async def test_an_empty_query_vector_returns_nothing(vector_store) -> None:
    assert await vector_store.search([], "test-embed") == []


async def test_deleting_a_post_removes_only_its_chunks(vector_store) -> None:
    await vector_store.upsert_chunks(
        post_id="p1", model_name="test-embed", chunks=chunks(2), payload={}
    )
    await vector_store.upsert_chunks(
        post_id="p2", model_name="test-embed", chunks=chunks(2, seed=0.9), payload={}
    )

    await vector_store.delete_posts(["p1"])

    hits = await vector_store.search(vec(0.5), "test-embed", limit=50, score_threshold=0.0)
    assert {hit.payload["post_id"] for hit in hits} == {"p2"}


async def test_deleting_several_posts_at_once(vector_store) -> None:
    for post_id in ("p1", "p2", "p3"):
        await vector_store.upsert_chunks(
            post_id=post_id, model_name="test-embed", chunks=chunks(1), payload={}
        )

    await vector_store.delete_posts(["p1", "p2"])

    hits = await vector_store.search(vec(0.5), "test-embed", limit=50, score_threshold=0.0)
    assert {hit.payload["post_id"] for hit in hits} == {"p3"}


async def test_deleting_nothing_is_a_no_op(vector_store) -> None:
    assert await vector_store.delete_posts([]) == 0


async def test_different_dimensions_land_in_different_collections(vector_store) -> None:
    await vector_store.upsert_chunks(
        post_id="p1", model_name="test-embed", chunks=chunks(1), payload={}
    )
    await vector_store.upsert_chunks(
        post_id="p1",
        model_name="test-embed",
        chunks=[Chunk(chunk_index=0, chunk_text="다른 차원", vector=[0.5] * 16)],
        payload={},
    )

    assert vector_store.collection_for("test-embed", 8) != vector_store.collection_for(
        "test-embed", 16
    )
    assert len(await vector_store.search([0.5] * 16, "test-embed", score_threshold=0.0)) == 1


async def test_inconsistent_dimensions_within_one_post_are_rejected(vector_store) -> None:
    mixed = [
        Chunk(chunk_index=0, chunk_text="a", vector=vec(0.5)),
        Chunk(chunk_index=1, chunk_text="b", vector=[0.5] * 4),
    ]

    with pytest.raises(ValueError, match="inconsistent"):
        await vector_store.upsert_chunks(
            post_id="p1", model_name="test-embed", chunks=mixed, payload={}
        )
