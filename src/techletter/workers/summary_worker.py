"""summary-worker — 브라우저를 띄우는 유일한 프로세스.

한 번에 잡 하나만 처리한다(동시성 1). 브라우저가 메모리를 많이 쓰고
같은 호스트에 요약·임베딩·API가 함께 올라가 있다.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from techletter.core.jobs.runner import JobRunner
from techletter.core.jobs.types import JobType
from techletter.core.llm.budget import DailyBudget
from techletter.core.llm.chat import LangChainChatClient, LlmGateway, RoutingChatClient
from techletter.core.llm.router import ModelRouter
from techletter.core.llm.scouter import ScouterClient
from techletter.core.logging import get_logger
from techletter.summary.handlers import ContentFetchHandler, SummaryRequestedHandler
from techletter.summary.pipeline import SummaryPipeline
from techletter.summary.renderer import PlaywrightRenderer, Renderer
from techletter.summary.summarizer import Summarizer
from techletter.workers.runtime import Heartbeat

if TYPE_CHECKING:  # pragma: no cover
    from techletter.container import Container

__all__ = ["build_summarizer", "build_summary_worker"]

logger = get_logger(__name__)


def build_summarizer(container: Container) -> Summarizer:
    """요약 워커와 주제 재분류 CLI가 같은 모델 순서와 예산을 쓴다."""
    settings = container.settings
    # 요약은 Gemini를 1순위로 쓰고 예산이 다하면 OpenRouter 무료 모델로
    # 넘어간다. 후보 목록에 두 provider의 모델 id가 섞여 오므로,
    # 하나의 provider만 아는 LangChainChatClient 로는 처리할 수 없다 —
    # `RoutingChatClient`가 model_id를 보고 알맞은 클라이언트로 나눠 보낸다.
    llm = LlmGateway(
        ModelRouter(
            settings.router,
            ScouterClient(settings.router, container.db),
            container.model_stats,
        ),
        RoutingChatClient(
            settings.summary_llm.model_name,
            LangChainChatClient(settings.summary_llm),
            LangChainChatClient(settings.chat_llm),
        ),
    )
    return Summarizer(
        llm,
        settings.summary,
        budget=DailyBudget(container.db, reset_utc_hour=settings.router.quota_reset_utc_hour),
        primary_model=settings.summary_llm.model_name,
        primary_provider=settings.summary_llm.provider,
        daily_limit=settings.router.summary_daily_budget,
    )


def build_summary_worker(container: Container) -> tuple[JobRunner, Renderer]:
    heartbeat = Heartbeat()
    renderer = PlaywrightRenderer(container.settings.summary, container.http.get())
    summarizer = build_summarizer(container)
    pipeline = SummaryPipeline(renderer, summarizer, container.http.get())
    runner = JobRunner(
        container.queue,
        container.settings.jobs,
        {
            # 같은 워커가 두 단계를 모두 맡는다 — 가져오기는 브라우저가, 요약은 LLM이 필요하다.
            JobType.CONTENT_FETCH_REQUESTED: ContentFetchHandler(
                container.posts, pipeline, container.queue
            ),
            JobType.SUMMARY_REQUESTED: SummaryRequestedHandler(
                container.posts, pipeline, container.queue
            ),
        },
        worker_id=f"summary-{uuid.uuid4().hex[:8]}",
        on_tick=heartbeat.touch,
    )
    return runner, renderer
