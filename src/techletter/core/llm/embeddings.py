"""임베딩 클라이언트.

챗봇 질의 임베딩과 워커의 문서 임베딩이 **같은 모델**을 써야 벡터 공간이
맞는다. 그래서 모델 이름을 설정 한 곳에서 받는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from techletter.core.errors import QuotaExceededError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.settings import EmbeddingLlmSettings

__all__ = ["LangChainEmbedder"]

logger = get_logger(__name__)

# 구글 무료 등급의 일일 한도(RPD 1000). 분당 한도(RPM 100)와 같은 metric,
# 같은 429를 쓰고 `quotaId`만 다르다(`...PerDayPer...` / `...PerMinutePer...`).
_DAILY_QUOTA_MARKER = "PerDay"


def _raise_classified(exc: Exception) -> None:
    """일일 한도는 `QuotaExceededError`로 바꾼다.

    그대로 두면 재시도 가능한 실패로 분류돼 한도가 풀리기 전에 재시도 횟수를
    다 태우고 잡이 dead가 된다. 분당 한도는 곧 풀리므로 원래 예외를 둔다.
    """
    message = f"{type(exc).__name__}: {exc}"
    if _DAILY_QUOTA_MARKER in message:
        raise QuotaExceededError(message) from exc
    raise exc


class LangChainEmbedder:
    def __init__(self, settings: EmbeddingLlmSettings) -> None:
        self._settings = settings
        self._client: Any = None

    def _get(self) -> Any:
        if self._client is not None:
            return self._client
        from langchain_google_genai import GoogleGenerativeAIEmbeddings  # noqa: PLC0415

        # 타임아웃은 client_args로 줘야 한다. `request_options`는 받기만 하고
        # 쓰지 않아서(langchain-google-genai 4.x), 기본값이면 타임아웃이 아예 없다.
        self._client = GoogleGenerativeAIEmbeddings(
            model=self._settings.model_name,
            api_key=self._settings.api_key,
            client_args={"timeout": self._settings.timeout_seconds},
        )
        return self._client

    async def embed_query(self, text: str) -> list[float]:
        return await self._get().aembed_query(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            return await self._get().aembed_documents(texts)
        except Exception as exc:
            _raise_classified(exc)
            raise  # pragma: no cover — _raise_classified는 항상 던진다
