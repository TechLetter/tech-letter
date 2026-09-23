"""임베딩 파이프라인.

청크는 포스트마다 고유해 캐시를 두지 않는다 — 같은 청크가 두 번 나오는
일이 사실상 없어 적중률이 의미 없다.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.db.qdrant import Chunk
from techletter.core.errors import PermanentError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from techletter.core.llm.embeddings import LangChainEmbedder
    from techletter.embedding.chunker import Chunker
    from techletter.settings import EmbeddingSettings

__all__ = ["ChunkRateLimiter", "EmbeddingPipeline", "EmbeddingResult"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    chunks: list[Chunk]
    model_name: str
    vector_dimension: int


class ChunkRateLimiter:
    """최근 1분 동안 보낸 청크 수를 `per_minute` 이하로 묶는다.

    구글 무료 등급은 배치 안의 텍스트 하나하나를 요청 한 번으로 센다(RPM 100).
    포스트 하나가 평균 12청크라 몰아서 적재하면 분당 한도를 바로 넘기고, 429는
    재시도 횟수를 태워 잡을 dead로 보낸다. 넘기기 전에 기다리는 편이 싸다.
    `per_minute`가 0 이하면 제한하지 않는다.
    """

    WINDOW_SECONDS = 60.0

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._sent: deque[tuple[float, int]] = deque()
        self._used = 0
        self._lock = asyncio.Lock()

    @property
    def per_minute(self) -> int:
        return self._per_minute

    def _expire(self, now: float) -> None:
        while self._sent and now - self._sent[0][0] >= self.WINDOW_SECONDS:
            self._used -= self._sent.popleft()[1]

    async def acquire(self, count: int) -> None:
        """`count`개를 보내도 한도 안에 들 때까지 기다린 뒤 장부에 적는다."""
        if self._per_minute <= 0:
            return
        count = min(count, self._per_minute)
        async with self._lock:
            now = self._clock()
            self._expire(now)
            while self._used + count > self._per_minute:
                await self._sleep(self._sent[0][0] + self.WINDOW_SECONDS - now)
                now = self._clock()
                self._expire(now)
            self._sent.append((now, count))
            self._used += count


class EmbeddingPipeline:
    def __init__(
        self,
        chunker: Chunker,
        embedder: LangChainEmbedder,
        settings: EmbeddingSettings,
        model_name: str,
        limiter: ChunkRateLimiter | None = None,
    ) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._settings = settings
        self._model_name = model_name
        self._limiter = limiter or ChunkRateLimiter(settings.embed_chunks_per_minute)

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
        """배치로 나눠 호출한다. 긴 글 하나가 요청 하나로 몰리지 않게.

        배치 하나가 분당 한도보다 크면 기다려도 못 보내므로 배치를 한도에 맞춘다.
        """
        size = max(1, self._settings.embed_batch_size)
        if self._limiter.per_minute > 0:
            size = min(size, self._limiter.per_minute)
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), size):
            batch = chunks[start : start + size]
            await self._limiter.acquire(len(batch))
            vectors.extend(await self._embedder.embed_documents(batch))
        logger.debug(
            "embedded chunks", extra={"chunks": len(chunks), "batches": -(-len(chunks) // size)}
        )
        return vectors
