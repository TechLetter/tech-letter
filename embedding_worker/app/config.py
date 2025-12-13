from __future__ import annotations

import os
from dataclasses import dataclass

from common.llm.factory import EmbeddingConfig, LlmProvider


EMBEDDING_WORKER_LLM_PROVIDER = "EMBEDDING_WORKER_LLM_PROVIDER"
EMBEDDING_WORKER_LLM_MODEL_NAME = "EMBEDDING_WORKER_LLM_MODEL_NAME"
EMBEDDING_WORKER_LLM_API_KEY = "EMBEDDING_WORKER_LLM_API_KEY"
EMBEDDING_WORKER_LLM_BASE_URL = "EMBEDDING_WORKER_LLM_BASE_URL"
EMBEDDING_WORKER_CHUNK_SIZE = "EMBEDDING_WORKER_CHUNK_SIZE"
EMBEDDING_WORKER_CHUNK_OVERLAP = "EMBEDDING_WORKER_CHUNK_OVERLAP"


@dataclass(slots=True)
class ChunkConfig:
    """텍스트 청킹 설정."""

    chunk_size: int = 1000
    chunk_overlap: int = 200


@dataclass(slots=True)
class AppConfig:
    """embedding-worker 전체 설정."""

    embedding: EmbeddingConfig
    chunk: ChunkConfig


def load_embedding_config() -> EmbeddingConfig:
    """LLM provider 기반 임베딩 설정을 로드한다."""

    provider_raw = os.getenv(EMBEDDING_WORKER_LLM_PROVIDER) or "google"
    provider = LlmProvider.from_str(provider_raw)

    model = os.getenv(EMBEDDING_WORKER_LLM_MODEL_NAME)
    if not model:
        raise RuntimeError(
            f"{EMBEDDING_WORKER_LLM_MODEL_NAME} environment variable is required for embedding-worker",
        )

    api_key = os.getenv(EMBEDDING_WORKER_LLM_API_KEY) or None

    base_url = os.getenv(EMBEDDING_WORKER_LLM_BASE_URL) or None

    return EmbeddingConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def load_chunk_config() -> ChunkConfig:
    chunk_size_raw = os.getenv(EMBEDDING_WORKER_CHUNK_SIZE)
    if not chunk_size_raw:
        chunk_size = 1000
    else:
        try:
            chunk_size = int(chunk_size_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"{EMBEDDING_WORKER_CHUNK_SIZE} must be an integer if set, got: {chunk_size_raw!r}"
            ) from exc

    chunk_overlap_raw = os.getenv(EMBEDDING_WORKER_CHUNK_OVERLAP)
    if not chunk_overlap_raw:
        chunk_overlap = 200
    else:
        try:
            chunk_overlap = int(chunk_overlap_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"{EMBEDDING_WORKER_CHUNK_OVERLAP} must be an integer if set, got: {chunk_overlap_raw!r}"
            ) from exc

    return ChunkConfig(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def load_config() -> AppConfig:
    """embedding-worker 설정을 로드하여 AppConfig로 반환한다."""

    embedding_config = load_embedding_config()
    chunk_config = load_chunk_config()
    return AppConfig(embedding=embedding_config, chunk=chunk_config)
