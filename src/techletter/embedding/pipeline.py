"""임베딩 파이프라인.

**캐시가 없다**(D17). 현행 `embedding_cache` 컬렉션은 1,688MB로 DB의 84%를
차지했는데(ISSUE-003) 같은 청크가 두 번 나오는 일이 사실상 없어 적중률이
의미 없었다. 청크는 포스트마다 고유하다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.db.qdrant import Chunk
from techletter.core.errors import PermanentError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.llm.embeddings import LangChainEmbedder
    from techletter.embedding.chunker import Chunker
    from techletter.settings import EmbeddingSettings

__all__ = ["EmbeddingPipeline", "EmbeddingResult"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    chunks: list[Chunk]
    model_name: str
    vector_dimension: int


class EmbeddingPipeline:
    def __init__(
        self,
        chunker: Chunker,
        embedder: LangChainEmbedder,
        settings: EmbeddingSettings,
        model_name: str,
    ) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._settings = settings
        self._model_name = model_name

    async def run(self, text: str) -> EmbeddingResult:
        """본문을 벡터로 만든다.

        청크가 하나도 안 나오면 재시도해도 같다 — 본문이 비었다는 뜻이다.
        `PermanentError`로 올려 잡을 바로 dead로 보낸다.
        """
        chunks = self._chunker.split(text)
        if not chunks:
            raise PermanentError("no text to embed", reason="empty_body")

        vectors = await self._embed_in_batches(chunks)
        if len(vectors) != len(chunks):
            # 개수가 어긋나면 청크와 벡터의 짝이 깨진다. 잘못된 벡터를
            # 저장하느니 실패시킨다.
            msg = f"embedding count mismatch: {len(vectors)} vectors for {len(chunks)} chunks"
            raise RuntimeError(msg)

        dimension = len(vectors[0])
        if dimension <= 0:
            msg = "embedding provider returned empty vectors"
            raise RuntimeError(msg)

        return EmbeddingResult(
            chunks=[
                Chunk(chunk_index=index, chunk_text=text, vector=vector)
                for index, (text, vector) in enumerate(zip(chunks, vectors, strict=True))
            ],
            model_name=self._model_name,
            vector_dimension=dimension,
        )

    async def _embed_in_batches(self, chunks: list[str]) -> list[list[float]]:
        """배치로 나눠 호출한다. 긴 글 하나가 요청 하나로 몰리지 않게."""
        size = max(1, self._settings.embed_batch_size)
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), size):
            batch = chunks[start : start + size]
            vectors.extend(await self._embedder.embed_documents(batch))
        logger.debug(
            "embedded chunks", extra={"chunks": len(chunks), "batches": -(-len(chunks) // size)}
        )
        return vectors
