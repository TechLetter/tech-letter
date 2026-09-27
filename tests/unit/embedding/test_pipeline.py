"""청킹·임베딩 — 캐시 없이."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError, QuotaExceededError
from techletter.embedding.chunker import Chunker
from techletter.embedding.pipeline import BUDGET_KEY, ChunkRateLimiter, EmbeddingPipeline
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


def test_chunks_are_sized_for_the_free_tier_quota() -> None:
    """무료 등급은 청크 하나를 요청 한 번으로 센다. 2026-09-27에 1000자에서 2000자로 늘렸다.

    기존 벡터(1000자)는 그대로 두고 새 글부터 적용한다. 크기가 섞이면 점수 분포가
    조금 달라질 뿐 검색은 된다. 다시 바꿀 때는 이 트레이드오프를 보고 정한다.
    """
    defaults = EmbeddingSettings()

    assert defaults.chunk_size == 2000
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


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


async def test_the_limiter_waits_once_the_minute_is_full() -> None:
    """구글은 청크 하나를 요청 한 번으로 센다. 분당 한도를 넘기기 전에 기다린다."""
    clock = FakeClock()
    limiter = ChunkRateLimiter(10, clock=clock, sleep=clock.sleep)

    await limiter.acquire(6)
    clock.now = 20.0
    await limiter.acquire(4)
    assert clock.slept == []

    await limiter.acquire(3)
    assert clock.slept == [40.0]  # 첫 6개가 1분 창을 벗어나는 시점
    assert clock.now == 60.0


async def test_a_zero_limit_never_waits() -> None:
    clock = FakeClock()
    limiter = ChunkRateLimiter(0, clock=clock, sleep=clock.sleep)

    for _ in range(5):
        await limiter.acquire(1000)

    assert clock.slept == []


async def test_batches_shrink_to_fit_the_minute_limit(settings) -> None:
    """배치 하나가 분당 한도보다 크면 아무리 기다려도 못 보낸다."""
    settings.embed_batch_size = 64
    clock = FakeClock()
    embedder = FakeEmbedder()
    pipeline = EmbeddingPipeline(
        Chunker(settings),
        embedder,  # type: ignore[arg-type]
        settings,
        "m",
        ChunkRateLimiter(3, clock=clock, sleep=clock.sleep),
    )

    await pipeline.run("문장입니다. " * 100)

    assert embedder.batches and all(size <= 3 for size in embedder.batches)
    assert clock.slept  # 3개를 넘는 순간부터 다음 1분을 기다렸다


# ── 하루 청크 예산 ──────────────────────────────────────────────────
class FakeBudget:
    def __init__(self, used: int = 0) -> None:
        self.used = used

    async def remaining(self, provider: str, limit: int) -> int:
        assert provider == BUDGET_KEY
        return max(limit - self.used, 0)

    async def consume(self, provider: str, amount: int = 1) -> int:
        self.used += amount
        return self.used


async def test_embedding_is_counted_against_the_daily_budget() -> None:
    settings = EmbeddingSettings(chunk_size=100, chunk_overlap=10, daily_chunk_budget=50)  # type: ignore[call-arg]
    budget = FakeBudget()
    pipeline = EmbeddingPipeline(Chunker(settings), FakeEmbedder(), settings, "m", budget=budget)  # type: ignore[arg-type]

    result = await pipeline.run("가나다 " * 60)

    assert budget.used == len(result.chunks)


async def test_an_exhausted_budget_defers_without_calling_the_api() -> None:
    settings = EmbeddingSettings(chunk_size=100, chunk_overlap=10, daily_chunk_budget=50)  # type: ignore[call-arg]
    embedder = FakeEmbedder()
    pipeline = EmbeddingPipeline(
        Chunker(settings),
        embedder,  # type: ignore[arg-type]
        settings,
        "m",
        budget=FakeBudget(used=48),  # type: ignore[arg-type]
    )

    with pytest.raises(QuotaExceededError) as caught:
        await pipeline.run("가나다 " * 60)

    assert embedder.batches == []
    assert caught.value.reset_at is not None
    assert caught.value.reset_at.hour == 7
