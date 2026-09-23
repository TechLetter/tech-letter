"""임베딩 클라이언트 — 외부 호출에 타임아웃이 실제로 걸리는지."""

from __future__ import annotations

from typing import Any

import pytest

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
