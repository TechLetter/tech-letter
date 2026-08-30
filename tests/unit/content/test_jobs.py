"""잡 enqueue 헬퍼 — 특히 우선순위 전달.

어드민 API와 CLI 백필 명령이 `priority`를 받아 놓고도
`enqueue_summary_requested`/`enqueue_embedding_requested` 호출에서 조용히
버린 적이 있다. 그러면 백필이 신규 수집물과 같은 우선순위로 큐에 쌓여버린다.
헬퍼가 `priority`를 그대로 넘기는지 여기서 고정한다.
"""

from __future__ import annotations

from techletter.content.jobs import enqueue_embedding_requested, enqueue_summary_requested
from techletter.content.models import Post
from techletter.core.jobs.models import PRIORITY_BACKFILL, PRIORITY_NORMAL
from techletter.core.jobs.types import JobType


class FakeQueue:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def enqueue(self, job_type, key, payload=None, *, priority=PRIORITY_NORMAL, **kwargs):
        self.calls.append({"type": job_type, "key": key, "priority": priority})
        return object()


def post(post_id: str = "6a83a8f5d34e63d870811f92") -> Post:
    from bson import ObjectId

    saved = Post(title="t", link="https://a.test/1", blog_name="Alpha")
    saved.id = ObjectId(post_id)
    return saved


async def test_summary_enqueue_defaults_to_normal_priority() -> None:
    """RSS 수집이나 수동 등록은 기본 우선순위를 쓴다."""
    queue = FakeQueue()

    await enqueue_summary_requested(queue, post())  # type: ignore[arg-type]

    assert queue.calls[0]["priority"] == PRIORITY_NORMAL
    assert queue.calls[0]["type"] == JobType.SUMMARY_REQUESTED


async def test_summary_enqueue_forwards_an_explicit_priority() -> None:
    """백필 호출자가 넘긴 priority가 실제로 queue.enqueue까지 전달돼야 한다."""
    queue = FakeQueue()

    await enqueue_summary_requested(queue, post(), priority=PRIORITY_BACKFILL)  # type: ignore[arg-type]

    assert queue.calls[0]["priority"] == PRIORITY_BACKFILL


async def test_embedding_enqueue_defaults_to_normal_priority() -> None:
    queue = FakeQueue()

    await enqueue_embedding_requested(queue, "6a83a8f5d34e63d870811f92")  # type: ignore[arg-type]

    assert queue.calls[0]["priority"] == PRIORITY_NORMAL


async def test_embedding_enqueue_forwards_an_explicit_priority() -> None:
    queue = FakeQueue()

    await enqueue_embedding_requested(
        queue,  # type: ignore[arg-type]
        "6a83a8f5d34e63d870811f92",
        priority=PRIORITY_BACKFILL,
    )

    assert queue.calls[0]["priority"] == PRIORITY_BACKFILL
