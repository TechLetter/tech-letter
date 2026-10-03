"""summary-worker — 브라우저를 띄우는 유일한 프로세스.

한 번에 잡 하나만 처리한다(동시성 1). 브라우저가 메모리를 많이 쓰고
같은 호스트에 요약·임베딩·API가 함께 올라가 있다.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from techletter.content.icons import BlogIconRepository
from techletter.core.jobs.runner import JobRunner
from techletter.core.jobs.types import JobType
from techletter.core.llm.budget import DailyBudget
from techletter.core.llm.chat import LangChainChatClient, LlmGateway, RoutingChatClient
from techletter.core.llm.quota import QuotaGate, QuotaModel
from techletter.core.llm.router import ModelRouter
from techletter.core.llm.scouter import ScouterClient
from techletter.core.logging import get_logger
from techletter.explainer.generator import ExplainerGenerator
from techletter.summary.handlers import ContentFetchHandler, SummaryRequestedHandler
from techletter.summary.icons import BlogIconHandler
from techletter.summary.pipeline import SummaryPipeline
from techletter.summary.renderer import PlaywrightRenderer, Renderer
from techletter.summary.summarizer import Summarizer
from techletter.workers.runtime import Heartbeat

if TYPE_CHECKING:  # pragma: no cover
    from techletter.container import Container

__all__ = ["build_explainer", "build_summarizer", "build_summary_worker"]

logger = get_logger(__name__)


def build_summarizer(container: Container) -> Summarizer:
    """주제 재분류 CLI가 쓴다. 새 글은 `build_explainer`가 쉽게 읽기를 만든다."""
    return Summarizer(_summary_llm(container), container.settings.summary)


def build_explainer(container: Container) -> ExplainerGenerator:
    """요약 워커와 같은 모델 순서·한도로 쉽게 읽기를 만든다."""
    return ExplainerGenerator(_summary_llm(container))


def _summary_llm(container: Container) -> LlmGateway:
    """요약 워커와 주제 재분류 CLI가 같은 모델 순서와 예산을 쓴다.

    3 Flash → 3.5 Flash Lite → OpenRouter 무료 모델 순서다. 앞의 둘은 하루·분당
    한도 안에서만 부른다(`QuotaGate`). 한 모델이 503·429로 실패하면 다음으로 간다.
    """
    settings = container.settings
    router = settings.router
    google = settings.summary_llm.provider
    quota = QuotaGate(
        DailyBudget(container.db, reset_utc_hour=router.quota_reset_utc_hour),
        [
            # 1순위 장부 키는 예전 그대로(provider 이름) 둔다 — 오늘 쓴 양을 이어서 센다.
            QuotaModel(
                settings.summary_llm.model_name,
                google,
                router.summary_daily_budget,
                router.summary_primary_rpm,
            ),
            QuotaModel(
                router.summary_secondary_model,
                f"{google}:{router.summary_secondary_model}",
                router.summary_secondary_daily_budget,
                router.summary_secondary_rpm,
            ),
        ],
    )
    # 후보에 두 provider의 모델 id가 섞인다. `RoutingChatClient`가 model_id를 보고
    # 한도 모델은 Google 클라이언트로, 나머지는 OpenRouter 클라이언트로 보낸다.
    return LlmGateway(
        ModelRouter(router, ScouterClient(router, container.db), container.model_stats),
        RoutingChatClient(
            quota.model_ids,
            LangChainChatClient(settings.summary_llm),
            LangChainChatClient(settings.chat_llm),
        ),
        quota=quota,
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
                container.posts,
                pipeline,
                container.queue,
                build_explainer(container)
                if container.settings.summary.explainer_enabled
                else None,
            ),
            # 이미지 변환(Pillow)과 SVG를 그릴 브라우저가 이 워커 이미지에만 있다.
            JobType.BLOG_ICON_REQUESTED: BlogIconHandler(
                container.blogs,
                BlogIconRepository(container.db),
                container.http.get(),
                renderer.rasterize_svg,
            ),
        },
        worker_id=f"summary-{uuid.uuid4().hex[:8]}",
        on_tick=heartbeat.touch,
    )
    return runner, renderer
