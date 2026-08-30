"""본문 청킹.

청크 크기·겹침을 바꾸면 이미 만들어진 벡터와 기준이 달라져 검색 결과가
흔들린다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.settings import EmbeddingSettings

__all__ = ["Chunker"]

logger = get_logger(__name__)

# 문단 → 줄 → 문장 → 단어 순으로 자른다.
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


class Chunker:
    def __init__(self, settings: EmbeddingSettings) -> None:
        self._settings = settings
        self._splitter: Any = None

    def _get(self) -> Any:
        if self._splitter is None:
            from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: PLC0415

            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=self._settings.chunk_size,
                chunk_overlap=self._settings.chunk_overlap,
                length_function=len,
                separators=SEPARATORS,
            )
        return self._splitter

    def split(self, text: str) -> list[str]:
        """본문을 청크로 나눈다. 빈 조각은 버리고 개수에 상한을 둔다.

        상한이 필요한 이유: 본문이 최대 91K자다. 그대로 나누면 포스트 하나가
        벡터 수백 개를 만들고 임베딩 호출도 그만큼 늘어난다.
        """
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        chunks = [chunk.strip() for chunk in self._get().split_text(cleaned)]
        chunks = [chunk for chunk in chunks if chunk]

        limit = self._settings.max_chunks_per_post
        if len(chunks) > limit:
            logger.warning("chunk count capped", extra={"produced": len(chunks), "limit": limit})
            chunks = chunks[:limit]
        return chunks
