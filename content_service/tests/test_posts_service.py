from __future__ import annotations

from common.eventbus.topics import TOPIC_POST_EMBEDDING_DELETE_REQUESTED
from common.events.post import EventType
from content_service.app.services.posts_service import PostsService


class FakePostRepository:
    def __init__(self) -> None:
        self.deleted_ids: set[str] = set()

    def delete_by_id(self, id_value: str) -> bool:
        return id_value in self.deleted_ids


class FakeBlogRepository:
    pass


class FakeEventBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    def publish(self, topic: str, event: object) -> None:
        self.published.append((topic, event))


def test_delete_post_publishes_embedding_delete_request_when_deleted() -> None:
    post_repo = FakePostRepository()
    post_repo.deleted_ids.add("post-1")
    event_bus = FakeEventBus()
    service = PostsService(post_repo, FakeBlogRepository(), event_bus)

    deleted = service.delete_post("post-1")

    assert deleted is True
    assert len(event_bus.published) == 1
    topic, event = event_bus.published[0]
    assert topic == TOPIC_POST_EMBEDDING_DELETE_REQUESTED.base
    assert event.payload["type"] == EventType.POST_EMBEDDING_DELETE_REQUESTED
    assert event.payload["post_id"] == "post-1"


def test_delete_post_does_not_publish_embedding_delete_request_when_missing() -> None:
    event_bus = FakeEventBus()
    service = PostsService(FakePostRepository(), FakeBlogRepository(), event_bus)

    deleted = service.delete_post("missing")

    assert deleted is False
    assert event_bus.published == []
