"""embedding-worker — 벡터 생성과 Qdrant 저장."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from techletter.core.jobs.runner import JobRunner
from techletter.core.jobs.types import JobType
from techletter.core.llm.embeddings import LangChainEmbedder
from techletter.embedding.chunker import Chunker
from techletter.embedding.handlers import EmbeddingDeleteHandler, EmbeddingRequestedHandler
from techletter.embedding.pipeline import EmbeddingPipeline
from techletter.workers.runtime import Heartbeat

if TYPE_CHECKING:  # pragma: no cover
    from techletter.container import Container

__all__ = ["build_embedding_worker"]


def build_embedding_worker(container: Container) -> JobRunner:
    settings = container.settings
    heartbeat = Heartbeat()
    store = container.vector_store

    pipeline = EmbeddingPipeline(
        Chunker(settings.embedding),
        LangChainEmbedder(settings.embedding_llm),
        settings.embedding,
        settings.embedding_llm.model_name,
    )
    return JobRunner(
        container.queue,
        settings.jobs,
        {
            JobType.EMBEDDING_REQUESTED: EmbeddingRequestedHandler(
                container.posts, pipeline, store, container.queue
            ),
            JobType.EMBEDDING_DELETE_REQUESTED: EmbeddingDeleteHandler(store),
        },
        worker_id=f"embedding-{uuid.uuid4().hex[:8]}",
        on_tick=heartbeat.touch,
    )
