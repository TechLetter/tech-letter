"""summary-worker — 브라우저를 띄우는 유일한 프로세스.

한 번에 잡 하나만 처리한다(동시성 1). 브라우저가 메모리를 많이 쓰고
같은 호스트에 요약·임베딩·API가 함께 올라가 있다.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from techletter.core.jobs.runner import JobRunner
from techletter.core.jobs.types import JobType
from techletter.core.llm.chat import LangChainChatClient, LlmGateway, RoutingChatClient
from techletter.core.llm.router import ModelRouter
from techletter.core.llm.scouter import ScouterClient
from techletter.core.logging import get_logger
from techletter.summary.handlers import SummaryRequestedHandler
from techletter.summary.pipeline import SummaryPipeline
from techletter.summary.renderer import PlaywrightRenderer, Renderer, ScraperApiRenderer
from techletter.summary.summarizer import Summarizer
from techletter.workers.runtime import Heartbeat

if TYPE_CHECKING:  # pragma: no cover
    from techletter.container import Container

__all__ = ["build_renderer", "build_summary_worker"]

logger = get_logger(__name__)


def build_renderer(container: Container) -> Renderer:
    settings = container.settings.summary
    if settings.renderer_strategy == "scraperapi":
        key = settings.scraperapi_key
        if key is not None:
            return ScraperApiRenderer(key.get_secret_value(), container.http.get())
        # 키 없이 scraperapi를 고른 설정 실수. 요약을 통째로 멈추느니
        # 브라우저로 떨어진다.
        logger.warning("RENDERER_STRATEGY=scraperapi but no key; using playwright")
    return PlaywrightRenderer(settings)


def build_summary_worker(container: Container) -> tuple[JobRunner, Renderer]:
    settings = container.settings
    heartbeat = Heartbeat()

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
    renderer = build_renderer(container)
    pipeline = SummaryPipeline(renderer, Summarizer(llm, settings.summary), container.http.get())
    runner = JobRunner(
        container.queue,
        settings.jobs,
        {
            JobType.SUMMARY_REQUESTED: SummaryRequestedHandler(
                container.posts, pipeline, container.queue
            )
        },
        worker_id=f"summary-{uuid.uuid4().hex[:8]}",
        on_tick=heartbeat.touch,
    )
    return runner, renderer
