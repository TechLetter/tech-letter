"""청킹·임베딩 — 캐시 없이 (D17)."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError
from techletter.embedding.chunker import Chunker
from techletter.embedding.pipeline import EmbeddingPipeline
from techletter.settings import EmbeddingSettings


class FakeEmbedder:
    def __init__(self, dimension: int = 4) -> None:
        self.dimension = dimension
        self.batches: list[int] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(len(texts))
        return [[0.1] * self.dimension for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * self.dimension


@pytest.fixture
def settings() -> EmbeddingSettings:
    return EmbeddingSettings(chunk_size=100, chunk_overlap=10)  # type: ignore[call-arg]


def test_chunk_sizes_match_the_existing_vectors() -> None:
    """이미 만들어진 벡터와 기준이 같아야 검색 결과가 흔들리지 않는다."""
    defaults = EmbeddingSettings()

    assert defaults.chunk_size == 1000
    assert defaults.chunk_overlap == 200


def test_an_empty_body_yields_no_chunks(settings) -> None:
    assert Chunker(settings).split("   ") == []


def test_a_long_body_is_split(settings) -> None:
    chunks = Chunker(settings).split("문장입니다. " * 100)

    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_the_chunk_count_is_capped(settings) -> None:
    """본문 최대가 91K자다. 그대로 두면 포스트 하나가 벡터를 수백 개 만든다."""
    settings.max_chunks_per_post = 5

    assert len(Chunker(settings).split("문장입니다. " * 500)) == 5


async def test_an_empty_body_is_a_permanent_failure(settings) -> None:
    pipeline = EmbeddingPipeline(Chunker(settings), FakeEmbedder(), settings, "m")  # type: ignore[arg-type]

    with pytest.raises(PermanentError) as excinfo:
        await pipeline.run("")

    assert excinfo.value.reason == "empty_body"


async def test_chunks_and_vectors_are_paired_in_order(settings) -> None:
    pipeline = EmbeddingPipeline(Chunker(settings), FakeEmbedder(), settings, "m")  # type: ignore[arg-type]

    result = await pipeline.run("문장입니다. " * 60)

    assert [chunk.chunk_index for chunk in result.chunks] == list(range(len(result.chunks)))
    assert result.vector_dimension == 4
    assert all(len(chunk.vector) == 4 for chunk in result.chunks)


async def test_embedding_happens_in_batches(settings) -> None:
    settings.embed_batch_size = 2
    embedder = FakeEmbedder()
    pipeline = EmbeddingPipeline(Chunker(settings), embedder, settings, "m")  # type: ignore[arg-type]

    await pipeline.run("문장입니다. " * 100)

    assert all(size <= 2 for size in embedder.batches)
    assert len(embedder.batches) > 1


async def test_a_count_mismatch_fails_loudly(settings) -> None:
    """짝이 어긋난 벡터를 저장하느니 실패시킨다."""

    class Short(FakeEmbedder):
        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1] * 4]

    pipeline = EmbeddingPipeline(Chunker(settings), Short(), settings, "m")  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="mismatch"):
        await pipeline.run("문장입니다. " * 100)


async def test_empty_vectors_fail(settings) -> None:
    pipeline = EmbeddingPipeline(Chunker(settings), FakeEmbedder(dimension=0), settings, "m")  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="empty vectors"):
        await pipeline.run("문장입니다. " * 20)
