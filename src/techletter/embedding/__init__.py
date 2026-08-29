"""embedding 도메인 — 청킹·임베딩·벡터 저장.

❌ `cache.py` 는 없다. `embedding_cache` 컬렉션은 폐지했다(D17, ISSUE-003).
"""

from techletter.embedding.chunker import Chunker
from techletter.embedding.handlers import EmbeddingDeleteHandler, EmbeddingRequestedHandler
from techletter.embedding.pipeline import EmbeddingPipeline, EmbeddingResult

__all__ = [
    "Chunker",
    "EmbeddingDeleteHandler",
    "EmbeddingPipeline",
    "EmbeddingRequestedHandler",
    "EmbeddingResult",
]
