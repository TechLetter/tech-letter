"""벡터 저장소 장애를 도구 결과와 ERROR 로그로 낮추는 테스트."""

from __future__ import annotations

from typing import Any, cast

import pytest

from techletter.chat.agent.tools.vector_search import VectorSearchTool
from techletter.core.errors import VectorStoreUnavailableError


class Embedder:
    async def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2]


class UnavailableStore:
    async def search(self, *_: Any, **__: Any) -> None:
        raise VectorStoreUnavailableError("qdrant is unavailable")


@pytest.mark.asyncio
async def test_store_outage_is_a_failed_result_and_error_log(caplog: Any) -> None:
    tool = VectorSearchTool(
        embedder=Embedder(),
        store=cast(Any, UnavailableStore()),
        embedding_model="test-model",
        top_k=5,
        score_threshold=0.5,
    )

    with caplog.at_level("ERROR", logger="techletter.chat.agent.tools.vector_search"):
        result = await tool.search("질문")

    assert result.status == "failed"
    assert result.reason == "vector_store_unavailable"
    assert result.message == "관련 정보를 찾지 못했습니다."
    assert any(record.levelname == "ERROR" for record in caplog.records)
