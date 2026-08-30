"""core-worker — 가볍고 빠른 잡을 담당한다.

요약(브라우저)과 임베딩(GPU/외부 API)은 각자 프로세스를 쓴다. 여기서는
DB만 만지는 잡과 주기 작업을 돌린다.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from techletter.chat.handlers import CompressionRequestedHandler
from techletter.chat.memory import MemoryBuilder
from techletter.chat.repositories import ChatSessionRepository
from techletter.content.handlers import EmbeddingCompletedHandler, SummaryCompletedHandler
from techletter.content.rss import Aggregator, RssFeeder
from techletter.core.jobs.policy import dead_retryable_alert
from techletter.core.jobs.runner import JobRunner
from techletter.core.jobs.types import ErrorKind, JobType
from techletter.core.logging import get_logger
from techletter.workers.runtime import Heartbeat
from techletter.workers.scheduler import PeriodicTask, Scheduler

if TYPE_CHECKING:  # pragma: no cover
    from techletter.container import Container

__all__ = ["build_core_worker"]

logger = get_logger(__name__)

MAINTENANCE_INTERVAL_SECONDS = 60.0


class CoreWorker:
    """잡 러너와 스케줄러를 함께 돌린다."""

    def __init__(self, runner: JobRunner, scheduler: Scheduler) -> None:
        self._runner = runner
        self._scheduler = scheduler

    def request_stop(self) -> None:
        self._runner.request_stop()
        self._scheduler.request_stop()

    async def run_forever(self) -> None:
        import asyncio  # noqa: PLC0415

        await asyncio.gather(self._runner.run_forever(), self._scheduler.run_forever())


def build_core_worker(container: Container) -> CoreWorker:
    settings = container.settings
    posts, queue = container.posts, container.queue
    heartbeat = Heartbeat()

    aggregator = Aggregator(
        container.blogs,
        posts,
        RssFeeder(container.http),
        queue,
        batch_size=settings.rss.batch_size,
        failure_threshold=settings.rss.auto_disable_after_failures,
    )

    async def collect_feeds() -> None:
        await aggregator.run()

    async def maintenance() -> None:
        """죽은 워커가 잡고 있던 잡을 회수하고, dead 잡이 쌓이는지 살핀다.

        워커가 SIGKILL로 죽으면 `running` 상태의 잡이 영원히 남는다.
        """
        recovered = await queue.recover_stale()
        if recovered:
            logger.info("stale jobs recovered", extra={"count": recovered})

        dead_retryable = await queue.count_dead(ErrorKind.RETRYABLE)
        alert = dead_retryable_alert(dead_retryable, settings.jobs.dead_retryable_alert_threshold)
        if alert:
            logger.warning(alert, extra={"dead_retryable": dead_retryable})

    # LLM은 대화 압축에만 쓴다. 요약·임베딩은 전용 워커가 담당한다.
    from techletter.core.llm.chat import LangChainChatClient, LlmGateway  # noqa: PLC0415
    from techletter.core.llm.router import ModelRouter  # noqa: PLC0415
    from techletter.core.llm.scouter import ScouterClient  # noqa: PLC0415

    llm = LlmGateway(
        ModelRouter(
            settings.router,
            ScouterClient(settings.router, container.http.get()),
            container.model_stats,
        ),
        LangChainChatClient(settings.chat_llm),
    )
    sessions_repo = ChatSessionRepository(container.db)

    runner = JobRunner(
        queue,
        settings.jobs,
        {
            JobType.SUMMARY_COMPLETED: SummaryCompletedHandler(posts, queue),
            JobType.EMBEDDING_COMPLETED: EmbeddingCompletedHandler(posts),
            JobType.CHAT_COMPRESSION_REQUESTED: CompressionRequestedHandler(
                container.sessions, sessions_repo, MemoryBuilder(llm, settings.chat)
            ),
        },
        worker_id=f"core-{uuid.uuid4().hex[:8]}",
        on_tick=heartbeat.touch,
    )
    scheduler = Scheduler(
        [
            PeriodicTask("rss", settings.rss.interval_seconds, collect_feeds),
            PeriodicTask("maintenance", MAINTENANCE_INTERVAL_SECONDS, maintenance),
        ]
    )
    return CoreWorker(runner, scheduler)
