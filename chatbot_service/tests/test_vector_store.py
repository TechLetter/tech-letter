from __future__ import annotations

from dataclasses import dataclass

import pytest

from chatbot_service.app.vector_store import VectorStore


@dataclass
class FakeCollection:
    name: str


@dataclass
class FakeCollectionsResponse:
    collections: list[FakeCollection]


class FakeQdrantClient:
    def __init__(self) -> None:
        self.collections = [
            FakeCollection("tech-letter__model_a__3"),
            FakeCollection("other__model_a__3"),
            FakeCollection("tech-letter__model_b__3"),
        ]
        self.deleted_collection_names: list[str] = []
        self.raise_on_list: Exception | None = None
        self.raise_on_delete_collections: set[str] = set()

    def get_collections(self) -> FakeCollectionsResponse:
        if self.raise_on_list is not None:
            raise self.raise_on_list
        return FakeCollectionsResponse(collections=self.collections)

    def delete(self, *, collection_name, points_selector) -> None:
        if collection_name in self.raise_on_delete_collections:
            raise RuntimeError("delete failed")
        self.deleted_collection_names.append(collection_name)


def _vector_store(client: FakeQdrantClient) -> VectorStore:
    store = VectorStore.__new__(VectorStore)
    store._client = client
    store._base_collection_name = "tech-letter"
    store._known_collections = set()
    return store


def test_delete_by_post_id_deletes_matching_collections_only() -> None:
    client = FakeQdrantClient()
    store = _vector_store(client)

    store.delete_by_post_id("post-1")

    assert client.deleted_collection_names == [
        "tech-letter__model_a__3",
        "tech-letter__model_b__3",
    ]


def test_delete_by_post_id_raises_when_collection_list_fails() -> None:
    client = FakeQdrantClient()
    client.raise_on_list = RuntimeError("qdrant down")
    store = _vector_store(client)

    with pytest.raises(RuntimeError, match="failed to list qdrant collections"):
        store.delete_by_post_id("post-1")


def test_delete_by_post_id_raises_when_any_collection_delete_fails() -> None:
    client = FakeQdrantClient()
    client.raise_on_delete_collections.add("tech-letter__model_b__3")
    store = _vector_store(client)

    with pytest.raises(RuntimeError, match="tech-letter__model_b__3"):
        store.delete_by_post_id("post-1")

    assert client.deleted_collection_names == ["tech-letter__model_a__3"]
