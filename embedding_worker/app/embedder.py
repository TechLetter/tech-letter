from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from common.llm.factory import EmbeddingConfig, create_embedding
from common.llm.utils import normalize_model_name

from .config import ChunkConfig


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChunkWithEmbedding:
    """청킹된 텍스트와 임베딩 벡터."""

    chunk_index: int
    chunk_text: str
    vector: list[float]


class TextEmbedder:
    """텍스트를 청킹하고 임베딩을 생성하는 클래스."""

    def __init__(
        self,
        embedding_config: EmbeddingConfig,
        chunk_config: ChunkConfig,
    ) -> None:
        self._embedding_config = embedding_config
        self._chunk_config = chunk_config

        self._normalized_model_name = normalize_model_name(self._embedding_config.model)

        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_config.chunk_size,
            chunk_overlap=chunk_config.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        self._embeddings = create_embedding(embedding_config)

    @property
    def normalized_model_name(self) -> str:
        return self._normalized_model_name

    def chunk_text(self, text: str) -> list[str]:
        """텍스트를 청크로 분할한다."""
        chunks = self._text_splitter.split_text(text)
        logger.debug("split text into %d chunks", len(chunks))
        return chunks

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """텍스트 리스트에 대한 임베딩 벡터를 생성한다."""
        if not texts:
            return []

        vectors = self._embeddings.embed_documents(texts)
        logger.debug("generated %d embedding vectors", len(vectors))
        return vectors

    def embed_and_chunk(self, text: str) -> list[ChunkWithEmbedding]:
        """텍스트를 청킹하고 각 청크에 대한 임베딩을 생성한다."""
        chunks = self.chunk_text(text)
        if not chunks:
            logger.warning("no chunks generated from text")
            return []

        vectors = self.embed_texts(chunks)

        results = []
        for idx, (chunk_text, vector) in enumerate(zip(chunks, vectors)):
            results.append(
                ChunkWithEmbedding(
                    chunk_index=idx,
                    chunk_text=chunk_text,
                    vector=vector,
                )
            )

        logger.info("created %d chunk embeddings", len(results))
        return results
