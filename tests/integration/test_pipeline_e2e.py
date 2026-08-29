"""파이프라인 전체 — 가짜 RSS부터 공개 API 노출까지.

가짜 RSS → 수집 → 요약 잡 → (가짜 렌더러·LLM) → summary.completed →
core-worker → embedding.requested → (가짜 임베더) → Qdrant →
embedding.completed → core-worker → `GET /posts`.

각 단계를 개별 테스트가 이미 검증한다. 여기서 확인하는 것은 **잡이 실제로
서로를 이어 주는가**다. Kafka 토픽 6개를 잡 큐 하나로 바꾼 것의 핵심이다.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest

from techletter.content.handlers import EmbeddingCompletedHandler, SummaryCompletedHandler
from techletter.content.models import Blog, ListPostsFilter
from techletter.content.repositories import BlogRepository, PostRepository
from techletter.content.rss import Aggregator, RssFeeder
from techletter.core.http import HttpClients
from techletter.core.jobs.runner import JobRunner
from techletter.core.jobs.types import JobStatus, JobType
from techletter.core.pagination import Page
from techletter.embedding.chunker import Chunker
from techletter.embedding.handlers import EmbeddingDeleteHandler, EmbeddingRequestedHandler
from techletter.embedding.pipeline import EmbeddingPipeline
from techletter.settings import EmbeddingSettings, SummarySettings
from techletter.summary.handlers import SummaryRequestedHandler
from techletter.summary.pipeline import SummaryPipeline
from techletter.summary.summarizer import Summarizer

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "fixtures"
FEED = (FIXTURES / "rss" / "rss2.xml").read_text(encoding="utf-8")
ARTICLE = (FIXTURES / "html" / "article.html").read_text(encoding="utf-8")
DIM = 8


class FakeRenderer:
    """브라우저 대신 픽스처 HTML을 준다."""

    def __init__(self, html: str = ARTICLE) -> None:
        self.html = html
        self.urls: list[str] = []

    async def render(self, url: str) -> str:
        self.urls.append(url)
        return self.html

    async def aclose(self) -> None:
        return


class FakeSummaryLlm:
    async def complete_json(self, purpose, system, user, **kwargs) -> tuple[dict, str]:
        return (
            {
                "summary": "Kafka 컨슈머 리밸런싱을 줄이는 설정과 정적 멤버십을 정리한 글입니다.",
                "categories": ["Backend"],
                "tags": ["Kafka", "Consumer Group"],
                "error": None,
            },
            "fake/summary-model",
        )

    async def candidates(self, purpose) -> list[str]:
        return ["fake/summary-model"]


class FakeEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.5] * DIM for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.5] * DIM


@pytest.fixture
def http_clients() -> HttpClients:
    clients = HttpClients()
    clients._secure = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=FEED))
    )
    clients._insecure = clients._secure
    return clients


@pytest.fixture
async def pipeline_env(mongo_db, queue, vector_store, http_clients):
    """수집기 + 워커 러너 3종을 한 벌 조립한다."""
    posts, blogs = PostRepository(mongo_db), BlogRepository(mongo_db)
    await blogs.insert(
        Blog(name="Alpha", url="https://alpha.test", rss_url="https://alpha.test/rss")
    )

    renderer = FakeRenderer()
    embedding_settings = EmbeddingSettings(chunk_size=200, chunk_overlap=20)  # type: ignore[call-arg]

    aggregator = Aggregator(blogs, posts, RssFeeder(http_clients), queue, batch_size=10)
    summary_runner = JobRunner(
        queue,
        _job_settings(),
        {
            JobType.SUMMARY_REQUESTED: SummaryRequestedHandler(
                posts,
                SummaryPipeline(
                    renderer,  # type: ignore[arg-type]
                    Summarizer(FakeSummaryLlm(), SummarySettings()),  # type: ignore[arg-type]
                ),
                queue,
            )
        },
        worker_id="summary-test",
    )
    embedding_runner = JobRunner(
        queue,
        _job_settings(),
        {
            JobType.EMBEDDING_REQUESTED: EmbeddingRequestedHandler(
                posts,
                EmbeddingPipeline(
                    Chunker(embedding_settings),
                    FakeEmbedder(),  # type: ignore[arg-type]
                    embedding_settings,
                    "fake-embed",
                ),
                vector_store,
                queue,
            ),
            JobType.EMBEDDING_DELETE_REQUESTED: EmbeddingDeleteHandler(vector_store),
        },
        worker_id="embedding-test",
    )
    core_runner = JobRunner(
        queue,
        _job_settings(),
        {
            JobType.SUMMARY_COMPLETED: SummaryCompletedHandler(posts, queue),
            JobType.EMBEDDING_COMPLETED: EmbeddingCompletedHandler(posts),
        },
        worker_id="core-test",
    )

    async def drain() -> None:
        """더 이상 처리할 잡이 없을 때까지 세 러너를 돌린다."""
        for _ in range(50):
            worked = False
            for runner in (summary_runner, core_runner, embedding_runner):
                while await runner.run_once():
                    worked = True
            if not worked:
                return
        raise AssertionError("잡이 끝나지 않는다 — 루프를 만들었을 가능성")

    yield {
        "aggregator": aggregator,
        "drain": drain,
        "posts": posts,
        "blogs": blogs,
        "renderer": renderer,
        "store": vector_store,
        "db": mongo_db,
        "queue": queue,
    }
    await http_clients.aclose()


def _job_settings():
    from techletter.settings import JobSettings

    return JobSettings(JOB_POLL_INTERVAL_SECONDS=0.01, idle_backoff_seconds=0.02)  # type: ignore[call-arg]


# ── 전체 흐름 ───────────────────────────────────────────────────────
async def test_a_feed_item_becomes_a_published_post_with_vectors(pipeline_env) -> None:
    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()

    posts, total = await pipeline_env["posts"].list_posts(
        ListPostsFilter(summarized=True), Page(1, 10)
    )

    assert total == 2
    post = posts[0]
    assert post.status.ai_summarized is True
    assert post.status.embedded is True
    assert post.aisummary is not None
    assert "리밸런싱" in post.aisummary.summary
    assert post.aisummary.tags == ["Kafka", "Consumer Group"]
    assert post.embedding is not None
    assert post.embedding.chunk_count > 0
    assert post.embedding.model_name == "fake-embed"


async def test_the_vectors_are_searchable(pipeline_env) -> None:
    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()

    hits = await pipeline_env["store"].search(
        [0.5] * DIM, "fake-embed", limit=50, score_threshold=0.0
    )

    assert hits
    assert hits[0].payload["blog_name"] == "Alpha"
    assert hits[0].payload["link"].startswith("https://example.com/blog/")


async def test_every_job_finishes(pipeline_env) -> None:
    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()

    stats = await pipeline_env["queue"].stats()

    assert stats["by_status"].get("dead", 0) == 0
    assert stats["by_status"].get("pending", 0) == 0
    assert stats["by_status"]["done"] == 8  # 포스트 2건 × 잡 4종


async def test_the_renderer_is_called_with_the_feed_link(pipeline_env) -> None:
    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()

    assert pipeline_env["renderer"].urls == [
        "https://example.com/blog/scaling-search",
        "https://example.com/blog/korean-title",
    ]


async def test_a_second_collection_cycle_does_nothing(pipeline_env) -> None:
    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()
    before = await pipeline_env["db"]["jobs"].count_documents({})

    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()

    assert await pipeline_env["db"]["jobs"].count_documents({}) == before


# ── 실패 경로 ───────────────────────────────────────────────────────
async def test_a_bot_blocked_page_dies_without_retrying(pipeline_env, mongo_db) -> None:
    """영구 실패는 5번 재시도하지 않는다(ISSUE-001)."""
    pipeline_env["renderer"].html = (FIXTURES / "html" / "cloudflare.html").read_text(
        encoding="utf-8"
    )

    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()

    dead = [
        job
        async for job in mongo_db["jobs"].find(
            {"type": JobType.SUMMARY_REQUESTED.value, "status": JobStatus.DEAD.value}
        )
    ]
    assert len(dead) == 2
    assert all(job["attempt"] == 1 for job in dead)
    assert all(job["error_kind"] == "permanent" for job in dead)


async def test_a_permanent_failure_leaves_a_reason_on_the_post(pipeline_env) -> None:
    """어드민이 "왜 요약이 안 됐나"를 볼 수 있어야 한다(ISSUE-008)."""
    pipeline_env["renderer"].html = (FIXTURES / "html" / "cloudflare.html").read_text(
        encoding="utf-8"
    )

    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()

    posts, _ = await pipeline_env["posts"].list_posts(ListPostsFilter(), Page(1, 10))
    assert all(post.status.failed_reason for post in posts)
    assert all(post.status.ai_summarized is False for post in posts)


async def test_a_failed_summary_never_reaches_embedding(pipeline_env, mongo_db) -> None:
    pipeline_env["renderer"].html = (FIXTURES / "html" / "cloudflare.html").read_text(
        encoding="utf-8"
    )

    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()

    assert await mongo_db["jobs"].count_documents({"type": JobType.EMBEDDING_REQUESTED.value}) == 0


async def test_deleting_a_post_removes_its_vectors(pipeline_env) -> None:
    from techletter.content.jobs import enqueue_embedding_delete

    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()
    posts, _ = await pipeline_env["posts"].list_posts(ListPostsFilter(), Page(1, 10))
    target = str(posts[0].id)

    await enqueue_embedding_delete(pipeline_env["queue"], [target], key=f"post:{target}")
    await pipeline_env["drain"]()

    hits = await pipeline_env["store"].search(
        [0.5] * DIM, "fake-embed", limit=50, score_threshold=0.0
    )
    assert target not in {hit.payload["post_id"] for hit in hits}


# ── 재실행 안전성 ───────────────────────────────────────────────────
async def test_draining_twice_changes_nothing(pipeline_env) -> None:
    """잡은 최소 1회 전달이다. 두 번 돌아도 결과가 같아야 한다."""
    await pipeline_env["aggregator"].run()
    await pipeline_env["drain"]()
    first, _ = await pipeline_env["posts"].list_posts(ListPostsFilter(), Page(1, 10))

    await pipeline_env["drain"]()
    second, _ = await pipeline_env["posts"].list_posts(ListPostsFilter(), Page(1, 10))

    assert [p.embedding.chunk_count for p in first if p.embedding] == [
        p.embedding.chunk_count for p in second if p.embedding
    ]


async def test_a_stale_running_job_is_recovered(pipeline_env, mongo_db) -> None:
    """워커가 SIGKILL로 죽으면 running 상태의 잡이 남는다."""
    from datetime import timedelta

    from techletter.core.time import utcnow

    await pipeline_env["aggregator"].run()
    await mongo_db["jobs"].update_many(
        {},
        {
            "$set": {
                "status": JobStatus.RUNNING.value,
                "locked_by": f"dead-worker-{uuid.uuid4().hex[:6]}",
                "locked_at": utcnow() - timedelta(hours=2),
            }
        },
    )

    recovered = await pipeline_env["queue"].recover_stale()

    assert recovered == 2
    await pipeline_env["drain"]()
    _, total = await pipeline_env["posts"].list_posts(ListPostsFilter(summarized=True), Page(1, 10))
    assert total == 2
