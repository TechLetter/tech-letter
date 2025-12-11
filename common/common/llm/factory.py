from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Self

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.retrievers import BaseRetriever
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings


class LlmProvider(str, Enum):
    GOOGLE = "google"
    OPENAI = "openai"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"

    @classmethod
    def from_str(cls, value: str) -> Self:
        normalized = value.lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"unsupported LLM provider: {value}") from exc


@dataclass(slots=True)
class EmbeddingConfig:
    provider: LlmProvider
    model: str
    api_key: str | None = None
    base_url: str | None = None


@dataclass(slots=True)
class ChatModelConfig:
    provider: LlmProvider
    model: str
    temperature: float = 1.0
    api_key: str | None = None
    base_url: str | None = None
    max_retries: int = 0


@dataclass(slots=True)
class RetrieverConfig:
    embedding: EmbeddingConfig
    persist_directory: str
    collection_name: str
    k: int = 10


def _apply_api_key_env(provider: LlmProvider, api_key: str | None) -> None:
    if not api_key:
        return
    if provider is LlmProvider.GOOGLE:
        os.environ.setdefault("GOOGLE_API_KEY", api_key)
    elif provider is LlmProvider.OPENAI:
        os.environ.setdefault("OPENAI_API_KEY", api_key)
    elif provider is LlmProvider.OPENROUTER:
        os.environ.setdefault("OPENAI_API_KEY", api_key)
        os.environ.setdefault("OPENROUTER_API_KEY", api_key)


_EMBEDDING_FACTORIES: dict[LlmProvider, Callable[[EmbeddingConfig], Embeddings]] = {
    LlmProvider.GOOGLE: lambda cfg: GoogleGenerativeAIEmbeddings(model=cfg.model),
    LlmProvider.OPENAI: lambda cfg: OpenAIEmbeddings(
        model=cfg.model,
        base_url=cfg.base_url,
    ),
    LlmProvider.OLLAMA: lambda cfg: OllamaEmbeddings(
        model=cfg.model,
        base_url=cfg.base_url or "http://localhost:11434",
    ),
    LlmProvider.OPENROUTER: lambda cfg: OpenAIEmbeddings(
        model=cfg.model,
        base_url=cfg.base_url or "https://openrouter.ai/api/v1",
    ),
}


_CHAT_FACTORIES: dict[LlmProvider, Callable[[ChatModelConfig], BaseChatModel]] = {
    LlmProvider.GOOGLE: lambda cfg: ChatGoogleGenerativeAI(
        model=cfg.model,
        temperature=cfg.temperature,
        max_retries=cfg.max_retries,
    ),
    LlmProvider.OPENAI: lambda cfg: ChatOpenAI(
        model=cfg.model,
        temperature=cfg.temperature,
        base_url=cfg.base_url,
        max_retries=cfg.max_retries,
    ),
    LlmProvider.OLLAMA: lambda cfg: ChatOllama(
        model=cfg.model,
        temperature=cfg.temperature,
        base_url=cfg.base_url or "http://localhost:11434",
    ),
    LlmProvider.OPENROUTER: lambda cfg: ChatOpenAI(
        model=cfg.model,
        temperature=cfg.temperature,
        base_url=cfg.base_url or "https://openrouter.ai/api/v1",
        max_retries=cfg.max_retries,
    ),
}


def create_embedding(config: EmbeddingConfig) -> Embeddings:
    _apply_api_key_env(config.provider, config.api_key)
    try:
        factory = _EMBEDDING_FACTORIES[config.provider]
    except KeyError as exc:
        raise ValueError(f"unsupported embedding provider: {config.provider}") from exc
    return factory(config)


def create_chat_model(config: ChatModelConfig) -> BaseChatModel:
    _apply_api_key_env(config.provider, config.api_key)
    try:
        factory = _CHAT_FACTORIES[config.provider]
    except KeyError as exc:
        raise ValueError(f"unsupported chat provider: {config.provider}") from exc
    return factory(config)


def create_retriever(config: RetrieverConfig) -> BaseRetriever:
    os.makedirs(config.persist_directory, exist_ok=True)

    embeddings = create_embedding(config.embedding)
    vectordb = Chroma(
        persist_directory=config.persist_directory,
        embedding_function=embeddings,
        collection_name=config.collection_name,
    )
    return vectordb.as_retriever(search_kwargs={"k": config.k})
