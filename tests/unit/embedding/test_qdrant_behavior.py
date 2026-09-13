"""Qdrant 검색 장애와 재임베딩 정리 동작을 검증한다."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from techletter.core.db.qdrant import Chunk, VectorStore
from techletter.core.errors import VectorStoreUnavailableError
from techletter.settings import QdrantSettings


class CollectionNotFoundError(Exception):
    status_code = 404


class QueryClient:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def query_points(self, **_: Any) -> None:
        raise self._error


class SuccessfulQueryClient:
    async def query_points(self, **_: Any) -> SimpleNamespace:
        return SimpleNamespace(points=[])


class WriteClient:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def create_collection(self, **kwargs: Any) -> None:
        self.events.append(("create_collection", kwargs))

    async def create_payload_index(self, **kwargs: Any) -> None:
        self.events.append(("create_payload_index", kwargs))

    async def delete(self, **kwargs: Any) -> None:
        self.events.append(("delete", kwargs))

    async def upsert(self, **kwargs: Any) -> None:
        self.events.append(("upsert", kwargs))


def make_store(client: Any) -> VectorStore:
    settings = QdrantSettings(
        QDRANT_HOST="localhost",
        QDRANT_PORT=6333,
        QDRANT_COLLECTION_NAME="test_vectors",
    )
    return VectorStore(settings, client=cast(Any, client))


@pytest.mark.asyncio
async def test_missing_collection_degrades_to_empty() -> None:
    store = make_store(QueryClient(CollectionNotFoundError("collection not found")))

    assert await store.search([0.1, 0.2], "test-model") == []


@pytest.mark.asyncio
async def test_connection_failure_is_distinguishable_from_missing_collection() -> None:
    store = make_store(QueryClient(ConnectionError("qdrant is down")))

    with pytest.raises(VectorStoreUnavailableError) as raised:
        await store.search([0.1, 0.2], "test-model")

    assert isinstance(raised.value.__cause__, ConnectionError)


@pytest.mark.asyncio
async def test_search_does_not_mark_the_payload_index_as_checked() -> None:
    store = make_store(SuccessfulQueryClient())

    assert await store.search([0.1, 0.2], "test-model") == []
    assert store._known == set()


@pytest.mark.asyncio
async def test_reembedding_deletes_a_post_before_upsert() -> None:
    client = WriteClient()
    store = make_store(client)

    await store.upsert_chunks(
        post_id="post-1",
        model_name="test-model",
        chunks=[
            Chunk(chunk_index=0, chunk_text="첫 조각", vector=[0.1, 0.2]),
            Chunk(chunk_index=1, chunk_text="둘째 조각", vector=[0.2, 0.3]),
        ],
        payload={},
    )

    assert [event[0] for event in client.events] == [
        "create_collection",
        "create_payload_index",
        "delete",
        "upsert",
    ]
    index_call = client.events[1][1]
    assert index_call["field_name"] == "post_id"
    assert str(index_call["field_schema"]) == "keyword"

    delete_call = client.events[2][1]
    selector = delete_call["points_selector"]
    condition = selector.must[0]
    assert condition.key == "post_id"
    assert condition.match.value == "post-1"


@pytest.mark.asyncio
async def test_payload_index_is_checked_once_per_collection() -> None:
    client = WriteClient()
    store = make_store(client)
    name = store.collection_for("test-model", 2)

    await store._ensure_collection(name, 2)
    await store._ensure_collection(name, 2)

    assert [event[0] for event in client.events].count("create_payload_index") == 1
