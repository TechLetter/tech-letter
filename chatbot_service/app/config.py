from __future__ import annotations

import os
from dataclasses import dataclass

from common.llm.factory import ChatModelConfig, EmbeddingConfig, LlmProvider


CHATBOT_LLM_PROVIDER = "CHATBOT_LLM_PROVIDER"
CHATBOT_LLM_MODEL_NAME = "CHATBOT_LLM_MODEL_NAME"
CHATBOT_LLM_API_KEY = "CHATBOT_LLM_API_KEY"
CHATBOT_LLM_TEMPERATURE = "CHATBOT_LLM_TEMPERATURE"
CHATBOT_LLM_BASE_URL = "CHATBOT_LLM_BASE_URL"
CHATBOT_LLM_MAX_RETRIES = "CHATBOT_LLM_MAX_RETRIES"
CHATBOT_EMBEDDING_PROVIDER = "CHATBOT_EMBEDDING_PROVIDER"
CHATBOT_EMBEDDING_MODEL_NAME = "CHATBOT_EMBEDDING_MODEL_NAME"
CHATBOT_EMBEDDING_API_KEY = "CHATBOT_EMBEDDING_API_KEY"
CHATBOT_EMBEDDING_BASE_URL = "CHATBOT_EMBEDDING_BASE_URL"
CHATBOT_RAG_TOP_K = "CHATBOT_RAG_TOP_K"
CHATBOT_RAG_SCORE_THRESHOLD = "CHATBOT_RAG_SCORE_THRESHOLD"
QDRANT_HOST = "QDRANT_HOST"
QDRANT_PORT = "QDRANT_PORT"
QDRANT_COLLECTION_NAME = "QDRANT_COLLECTION_NAME"


@dataclass(slots=True)
class QdrantConfig:
    """Qdrant Vector DB 설정."""

    host: str
    port: int
    collection_name: str


@dataclass(slots=True)
class AppConfig:
    """chatbot-service 전체 설정."""

    llm: ChatModelConfig
    embedding: EmbeddingConfig
    rag: RAGConfig
    qdrant: QdrantConfig


@dataclass(slots=True)
class RAGConfig:
    """RAG 검색 설정."""

    top_k: int
    score_threshold: float


def load_chat_model_config() -> ChatModelConfig:
    """LLM provider 기반 채팅 모델 설정을 로드한다."""

    provider_raw = os.getenv(CHATBOT_LLM_PROVIDER) or "google"
    provider = LlmProvider.from_str(provider_raw)

    model = os.getenv(CHATBOT_LLM_MODEL_NAME)
    if not model:
        raise RuntimeError(
            f"{CHATBOT_LLM_MODEL_NAME} environment variable is required for chatbot-service",
        )

    api_key = os.getenv(CHATBOT_LLM_API_KEY) or None

    temperature_raw = os.getenv(CHATBOT_LLM_TEMPERATURE)
    if temperature_raw is None:
        temperature = 0.7
    else:
        try:
            temperature = float(temperature_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"{CHATBOT_LLM_TEMPERATURE} must be a float if set, got: {temperature_raw!r}"
            ) from exc

    base_url = os.getenv(CHATBOT_LLM_BASE_URL) or None

    max_retries_raw = os.getenv(CHATBOT_LLM_MAX_RETRIES)
    if not max_retries_raw:
        max_retries = 0
    else:
        try:
            max_retries = int(max_retries_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"{CHATBOT_LLM_MAX_RETRIES} must be an integer if set, got: {max_retries_raw!r}"
            ) from exc
        if max_retries < 0:
            raise RuntimeError(
                f"{CHATBOT_LLM_MAX_RETRIES} must be >= 0, got: {max_retries}"
            )

    return ChatModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        max_retries=max_retries,
    )


def load_embedding_config(llm_config: ChatModelConfig) -> EmbeddingConfig:
    """RAG 검색용 임베딩 설정을 로드한다."""

    provider_raw = os.getenv(CHATBOT_EMBEDDING_PROVIDER) or "google"
    provider = LlmProvider.from_str(provider_raw)

    model = os.getenv(CHATBOT_EMBEDDING_MODEL_NAME)
    if not model:
        raise RuntimeError(
            f"{CHATBOT_EMBEDDING_MODEL_NAME} environment variable is required for chatbot-service",
        )

    api_key = os.getenv(CHATBOT_EMBEDDING_API_KEY) or llm_config.api_key
    base_url = os.getenv(CHATBOT_EMBEDDING_BASE_URL) or llm_config.base_url

    return EmbeddingConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def load_rag_config() -> RAGConfig:
    top_k_raw = os.getenv(CHATBOT_RAG_TOP_K)
    if not top_k_raw:
        top_k = 5
    else:
        try:
            parsed_top_k = int(top_k_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"{CHATBOT_RAG_TOP_K} must be an integer if set, got: {top_k_raw!r}",
            ) from exc
        if parsed_top_k <= 0:
            raise RuntimeError(
                f"{CHATBOT_RAG_TOP_K} must be >= 1, got: {parsed_top_k}",
            )
        top_k = parsed_top_k

    threshold_raw = os.getenv(CHATBOT_RAG_SCORE_THRESHOLD)
    if threshold_raw in (None, ""):
        score_threshold = 0.5
    else:
        try:
            parsed_threshold = float(threshold_raw)
        except ValueError as exc:
            raise RuntimeError(
                f"{CHATBOT_RAG_SCORE_THRESHOLD} must be a float if set, got: {threshold_raw!r}",
            ) from exc
        if parsed_threshold < 0:
            raise RuntimeError(
                f"{CHATBOT_RAG_SCORE_THRESHOLD} must be >= 0, got: {parsed_threshold}",
            )
        score_threshold = parsed_threshold

    return RAGConfig(top_k=top_k, score_threshold=score_threshold)


def load_qdrant_config() -> QdrantConfig:
    host = os.getenv(QDRANT_HOST, "localhost")

    port_raw = os.getenv(QDRANT_PORT, "6333")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{QDRANT_PORT} must be an integer, got: {port_raw!r}"
        ) from exc
    if port <= 0:
        raise RuntimeError(f"{QDRANT_PORT} must be > 0, got: {port}")

    collection_name = os.getenv(QDRANT_COLLECTION_NAME, "tech_letter_posts")

    return QdrantConfig(
        host=host,
        port=port,
        collection_name=collection_name,
    )


def load_config() -> AppConfig:
    """chatbot-service 설정을 로드하여 AppConfig로 반환한다."""

    llm_config = load_chat_model_config()
    embedding_config = load_embedding_config(llm_config=llm_config)
    rag_config = load_rag_config()
    qdrant_config = load_qdrant_config()
    return AppConfig(
        llm=llm_config,
        embedding=embedding_config,
        rag=rag_config,
        qdrant=qdrant_config,
    )
