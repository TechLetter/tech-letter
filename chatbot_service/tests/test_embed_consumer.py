from __future__ import annotations

from dataclasses import dataclass

import pytest

from chatbot_service.app.event_handlers import embed_consumer
from common.eventbus.core import Event
from common.eventbus.topics import (
    TOPIC_POST_EMBEDDING,
    TOPIC_POST_EMBEDDING_DELETE_REQUESTED,
)
from common.events.post import EventType, PostEmbedResponseEvent


@dataclass
class FakeUpsertResult:
    chunk_count: int
    collection_name: str
    vector_dimension: int


class FakeVectorStore:
    def __init__(self) -> None:
        self.upsert_result = FakeUpsertResult(
            chunk_count=2,
            collection_name="tech-letter__model__3",
            vector_dimension=3,
        )
        self.raise_error: Exception | None = None
        self.raise_delete_error: Exception | None = None
        self.received_events: list[PostEmbedResponseEvent] = []
        self.deleted_post_ids: list[str] = []

    def upsert_post_embeddings(self, event: PostEmbedResponseEvent) -> FakeUpsertResult:
        if self.raise_error is not None:
            raise self.raise_error
        self.received_events.append(event)
        return self.upsert_result

    def delete_by_post_id(self, post_id: str) -> None:
        if self.raise_delete_error is not None:
            raise self.raise_delete_error
        self.deleted_post_ids.append(post_id)


class FakeKafkaEventBus:
    instances: list["FakeKafkaEventBus"] = []
    next_event: Event | None = None

    def __init__(self, brokers: str) -> None:
        self.brokers = brokers
        self.published: list[tuple[str, Event]] = []
        self.subscribe_calls: list[dict] = []
        self.closed = False
        self.__class__.instances.append(self)

    def subscribe(self, *, group_id, topic, handler, stop_flag) -> None:
        self.subscribe_calls.append(
            {
                "group_id": group_id,
                "topic": topic,
                "handler": handler,
                "stop_flag": stop_flag,
            }
        )
        if self.__class__.next_event is not None:
            handler(self.__class__.next_event)

    def publish(self, topic: str, event: Event) -> None:
        self.published.append((topic, event))

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def reset_fake_kafka_event_bus_state() -> None:
    FakeKafkaEventBus.instances = []
    FakeKafkaEventBus.next_event = None


def _patch_consumer_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    event: Event | None,
) -> None:
    FakeKafkaEventBus.instances = []
    FakeKafkaEventBus.next_event = event
    monkeypatch.setattr(embed_consumer, "get_brokers", lambda: "kafka:9092")
    monkeypatch.setattr(embed_consumer, "get_group_id", lambda: "chatbot-group")
    monkeypatch.setattr(embed_consumer, "KafkaEventBus", FakeKafkaEventBus)


def _run_consumer_once(
    monkeypatch: pytest.MonkeyPatch,
    *,
    event: Event,
    vector_store: FakeVectorStore | None = None,
    topic=None,
) -> tuple[FakeVectorStore, FakeKafkaEventBus, list[bool]]:
    local_vector_store = vector_store or FakeVectorStore()
    _patch_consumer_dependencies(monkeypatch, event=event)

    stop_flag = [False]
    if topic is None:
        embed_consumer.run_embed_consumer(stop_flag, local_vector_store)
    else:
        embed_consumer.run_embed_consumer(stop_flag, local_vector_store, topic)

    assert len(FakeKafkaEventBus.instances) == 1
    bus = FakeKafkaEventBus.instances[0]
    return local_vector_store, bus, stop_flag


def _build_embed_response_payload(*, event_type: str) -> dict:
    return {
        "id": "embed-response-1",
        "type": event_type,
        "timestamp": "2026-02-16T00:00:00Z",
        "source": "embedding-worker",
        "version": "1.0",
        "post_id": "post-1",
        "title": "테스트 포스트",
        "blog_name": "테스트 블로그",
        "link": "https://example.com/post-1",
        "published_at": "2026-02-15T00:00:00Z",
        "categories": ["AI"],
        "tags": ["RAG"],
        "chunks": [
            {
                "chunk_index": 0,
                "chunk_text": "첫 번째 청크",
                "vector": [0.1, 0.2, 0.3],
            },
            {
                "chunk_index": 1,
                "chunk_text": "두 번째 청크",
                "vector": [0.4, 0.5, 0.6],
            },
        ],
        "model_name": "text-embedding-3-small",
    }


def _build_embedding_delete_requested_payload() -> dict:
    return {
        "id": "embedding-delete-1",
        "type": EventType.POST_EMBEDDING_DELETE_REQUESTED,
        "timestamp": "2026-02-16T00:00:00Z",
        "source": "content-service",
        "version": "1.0",
        "post_id": "post-1",
    }


def test_run_embed_consumer_ignores_payload_that_is_not_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id="evt-1", payload="not-a-dict")
    vector_store, bus, _ = _run_consumer_once(monkeypatch, event=event)

    assert vector_store.received_events == []
    assert bus.published == []


def test_run_embed_consumer_ignores_non_target_event_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build_embed_response_payload(event_type=EventType.POST_SUMMARY_RESPONSE)
    event = Event(id="evt-2", payload=payload)
    vector_store, bus, _ = _run_consumer_once(monkeypatch, event=event)

    assert vector_store.received_events == []
    assert bus.published == []


def test_run_embed_consumer_publishes_applied_event_when_upsert_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build_embed_response_payload(event_type=EventType.POST_EMBEDDING_RESPONSE)
    event = Event(id="evt-3", payload=payload)
    vector_store, bus, stop_flag = _run_consumer_once(monkeypatch, event=event)

    assert len(vector_store.received_events) == 1
    assert vector_store.received_events[0].post_id == "post-1"

    assert len(bus.published) == 1
    topic, out_event = bus.published[0]
    assert topic == TOPIC_POST_EMBEDDING.base
    assert out_event.payload["type"] == EventType.POST_EMBEDDING_APPLIED
    assert out_event.payload["post_id"] == "post-1"
    assert out_event.payload["collection_name"] == "tech-letter__model__3"
    assert out_event.payload["vector_dimension"] == 3
    assert out_event.payload["chunk_count"] == 2

    assert len(bus.subscribe_calls) == 1
    subscribe_call = bus.subscribe_calls[0]
    assert subscribe_call["group_id"] == "chatbot-group"
    assert subscribe_call["topic"].base == TOPIC_POST_EMBEDDING.base
    assert subscribe_call["stop_flag"] is stop_flag
    assert callable(subscribe_call["handler"])
    assert bus.closed is True


def test_run_embed_consumer_deletes_embeddings_when_delete_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id="evt-delete-1", payload=_build_embedding_delete_requested_payload())
    vector_store, bus, _ = _run_consumer_once(
        monkeypatch,
        event=event,
        topic=TOPIC_POST_EMBEDDING_DELETE_REQUESTED,
    )

    assert vector_store.deleted_post_ids == ["post-1"]
    assert vector_store.received_events == []
    assert bus.published == []
    assert (
        bus.subscribe_calls[0]["topic"].base
        == TOPIC_POST_EMBEDDING_DELETE_REQUESTED.base
    )


def test_run_embed_consumer_raises_when_payload_schema_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(
        id="evt-4",
        payload={"type": EventType.POST_EMBEDDING_RESPONSE},
    )
    vector_store = FakeVectorStore()
    _patch_consumer_dependencies(monkeypatch, event=event)

    with pytest.raises(KeyError):
        embed_consumer.run_embed_consumer([False], vector_store)

    assert len(FakeKafkaEventBus.instances) == 1
    assert FakeKafkaEventBus.instances[0].closed is True


def test_run_embed_consumer_raises_when_upsert_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build_embed_response_payload(event_type=EventType.POST_EMBEDDING_RESPONSE)
    event = Event(id="evt-5", payload=payload)
    vector_store = FakeVectorStore()
    vector_store.raise_error = RuntimeError("upsert failed")
    _patch_consumer_dependencies(monkeypatch, event=event)

    with pytest.raises(RuntimeError, match="upsert failed"):
        embed_consumer.run_embed_consumer([False], vector_store)

    assert len(FakeKafkaEventBus.instances) == 1
    assert FakeKafkaEventBus.instances[0].closed is True


def test_run_embed_consumer_raises_when_delete_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = Event(id="evt-delete-2", payload=_build_embedding_delete_requested_payload())
    vector_store = FakeVectorStore()
    vector_store.raise_delete_error = RuntimeError("delete failed")
    _patch_consumer_dependencies(monkeypatch, event=event)

    with pytest.raises(RuntimeError, match="delete failed"):
        embed_consumer.run_embed_consumer(
            [False],
            vector_store,
            TOPIC_POST_EMBEDDING_DELETE_REQUESTED,
        )

    assert len(FakeKafkaEventBus.instances) == 1
    assert FakeKafkaEventBus.instances[0].closed is True


def test_run_embed_consumer_subscribes_and_closes_bus_without_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_consumer_dependencies(monkeypatch, event=None)

    stop_flag = [False]
    vector_store = FakeVectorStore()
    embed_consumer.run_embed_consumer(stop_flag, vector_store)

    assert len(FakeKafkaEventBus.instances) == 1
    bus = FakeKafkaEventBus.instances[0]
    assert bus.brokers == "kafka:9092"
    assert bus.closed is True
    assert len(bus.subscribe_calls) == 1

    subscribe_call = bus.subscribe_calls[0]
    assert subscribe_call["group_id"] == "chatbot-group"
    assert subscribe_call["topic"].base == TOPIC_POST_EMBEDDING.base
    assert subscribe_call["stop_flag"] is stop_flag
    assert callable(subscribe_call["handler"])
