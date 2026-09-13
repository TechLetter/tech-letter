"""재임베딩 시 기존 포인트 정리와 post_id payload 인덱스를 실제 Qdrant 로 검증한다."""

from __future__ import annotations

import pytest
from qdrant_client.http.models import PayloadSchemaType

from techletter.core.db.qdrant import Chunk

pytestmark = pytest.mark.integration

DIM = 8


def chunks(count: int, seed: float = 0.5) -> list[Chunk]:
    return [
        Chunk(
            chunk_index=index,
            chunk_text=f"조각 {index}",
            vector=[seed + index * 0.01] * DIM,
        )
        for index in range(count)
    ]


async def test_reembedding_removes_tail_chunks_and_preserves_other_posts(vector_store) -> None:
    await vector_store.upsert_chunks(
        post_id="post-a", model_name="wu04-model", chunks=chunks(5), payload={}
    )
    await vector_store.upsert_chunks(
        post_id="post-b", model_name="wu04-model", chunks=chunks(3, seed=0.9), payload={}
    )
    await vector_store.upsert_chunks(
        post_id="post-a", model_name="wu04-model", chunks=chunks(2, seed=0.7), payload={}
    )

    hits = await vector_store.search([0.5] * DIM, "wu04-model", limit=100, score_threshold=0.0)
    counts = {
        post_id: sum(hit.payload["post_id"] == post_id for hit in hits)
        for post_id in ("post-a", "post-b")
    }

    assert counts == {"post-a": 2, "post-b": 3}


async def test_post_id_payload_index_is_created_idempotently(vector_store) -> None:
    result = await vector_store.upsert_chunks(
        post_id="post-index", model_name="wu04-model", chunks=chunks(1), payload={}
    )

    collection = await vector_store._client.get_collection(result.collection_name)
    assert "post_id" in collection.payload_schema
    assert collection.payload_schema["post_id"].data_type == PayloadSchemaType.KEYWORD

    await vector_store._ensure_collection(result.collection_name, DIM)
    await vector_store._ensure_collection(result.collection_name, DIM)
