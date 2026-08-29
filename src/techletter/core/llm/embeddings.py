"""임베딩 클라이언트.

챗봇 질의 임베딩과 워커의 문서 임베딩이 **같은 모델**을 써야 벡터 공간이
맞는다. 그래서 모델 이름을 설정 한 곳에서 받는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.settings import LlmSettings

__all__ = ["LangChainEmbedder"]

logger = get_logger(__name__)


class LangChainEmbedder:
    def __init__(self, settings: LlmSettings) -> None:
        self._settings = settings
        self._client: Any = None

    def _get(self) -> Any:
        if self._client is not None:
            return self._client
        provider = self._settings.provider
        api_key = self._settings.api_key
        if provider == "google":
            from langchain_google_genai import GoogleGenerativeAIEmbeddings  # noqa: PLC0415

            self._client = GoogleGenerativeAIEmbeddings(
                model=self._settings.model_name, google_api_key=api_key
            )
        else:
            from langchain_openai import OpenAIEmbeddings  # noqa: PLC0415

            self._client = OpenAIEmbeddings(
                model=self._settings.model_name,
                base_url=self._settings.base_url,
                api_key=api_key,
            )
        return self._client

    async def embed_query(self, text: str) -> list[float]:
        return await self._get().aembed_query(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._get().aembed_documents(texts)
