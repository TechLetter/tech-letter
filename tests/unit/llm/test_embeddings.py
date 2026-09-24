"""임베딩 클라이언트 — 외부 호출에 타임아웃이 실제로 걸리는지."""

from __future__ import annotations

from typing import Any

import pytest

from techletter.core.errors import QuotaExceededError
from techletter.core.llm.embeddings import LangChainEmbedder
from techletter.settings import EmbeddingLlmSettings


def test_the_timeout_reaches_the_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """`request_options`는 라이브러리가 무시한다 — `client_args`로 넘겨야 한다."""
    import langchain_google_genai

    seen: dict[str, Any] = {}

    class Capture:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(langchain_google_genai, "GoogleGenerativeAIEmbeddings", Capture)
    settings = EmbeddingLlmSettings(_env_file=None, timeout_seconds=7)  # pyright: ignore[reportCallIssue]

    LangChainEmbedder(settings)._get()

    assert seen["client_args"] == {"timeout": 7}
    assert "request_options" not in seen


class _Failing:
    def __init__(self, message: str) -> None:
        self._message = message

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError(self._message)


def _embedder(message: str) -> LangChainEmbedder:
    embedder = LangChainEmbedder(EmbeddingLlmSettings(_env_file=None))  # pyright: ignore[reportCallIssue]
    embedder._client = _Failing(message)
    return embedder


async def test_the_daily_limit_waits_for_the_reset() -> None:
    """일일 한도를 재시도로 다루면 한도가 풀리기 전에 잡이 dead가 된다."""
    message = (
        "429 RESOURCE_EXHAUSTED embed_content_free_tier_requests, limit: 1000 "
        "'quotaId': 'EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier'"
    )

    with pytest.raises(QuotaExceededError):
        await _embedder(message).embed_documents(["x"])


async def test_the_minute_limit_stays_retryable() -> None:
    message = (
        "429 RESOURCE_EXHAUSTED embed_content_free_tier_requests, limit: 100 "
        "'quotaId': 'EmbedContentRequestsPerMinutePerUserPerProjectPerModel-FreeTier'"
    )

    with pytest.raises(RuntimeError) as excinfo:
        await _embedder(message).embed_documents(["x"])
    assert not isinstance(excinfo.value, QuotaExceededError)
