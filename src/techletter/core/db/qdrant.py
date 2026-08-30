"""Qdrant 벡터 저장소.

컬렉션 이름 규칙은 **운영 데이터에 이미 박혀 있어** 바꿀 수 없다:
`{base}__{model_key}__{dim}` (예: `tech_letter_posts__gemini-embedding-001__3072`).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    VectorParams,
)

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.settings import QdrantSettings

__all__ = ["Chunk", "SearchHit", "VectorStore", "collection_name_for", "normalize_model_name"]

logger = get_logger(__name__)

_NON_SLUG = re.compile(r"[^a-z0-9_\-]+")
_REPEATED_UNDERSCORE = re.compile(r"_+")
# 포인트 id를 만드는 네임스페이스. 같은 (post, model, dim, index)면 항상 같은 id가
# 나와야 재임베딩이 중복 포인트를 쌓지 않고 덮어쓴다.
_POINT_NAMESPACE = uuid.NAMESPACE_URL


def normalize_model_name(model_name: str) -> str:
    """provider prefix를 떼어 낸다. `google/gemini-...` → `gemini-...`.

    OpenRouter를 경유하면 prefix가 붙지만 모델은 같다. 컬렉션이 갈리면 안 된다.
    """
    if not model_name:
        return "unknown"
    value = model_name.strip()
    if "/" in value:
        value = value.rsplit("/", 1)[-1].strip()
    return value or "unknown"


def _model_key(model_name: str) -> str:
    key = _NON_SLUG.sub("_", normalize_model_name(model_name).lower())
    return _REPEATED_UNDERSCORE.sub("_", key).strip("_") or "unknown"


def collection_name_for(base: str, model_name: str, vector_dimension: int) -> str:
    return f"{base}__{_model_key(model_name)}__{vector_dimension}"


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_index: int
    chunk_text: str
    vector: list[float]


@dataclass(frozen=True, slots=True)
class SearchHit:
    score: float
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class UpsertResult:
    chunk_count: int
    collection_name: str
    vector_dimension: int


class VectorStore:
    def __init__(self, settings: QdrantSettings, client: AsyncQdrantClient | None = None) -> None:
        self._base = settings.collection_base
        self._client = client or AsyncQdrantClient(host=settings.host, port=settings.port)
        # 이미 만든 컬렉션을 기억해 매번 확인하지 않는다. 힌트일 뿐이라 틀려도 안전하다.
        self._known: set[str] = set()

    async def close(self) -> None:
        await self._client.close()

    async def ping(self) -> bool:
        await self._client.get_collections()
        return True

    def collection_for(self, model_name: str, vector_dimension: int) -> str:
        return collection_name_for(self._base, model_name, vector_dimension)

    async def _ensure_collection(self, name: str, vector_dimension: int) -> None:
        if name in self._known:
            return
        try:
            await self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=vector_dimension, distance=Distance.COSINE),
            )
        except Exception:
            # 워커 여러 개가 동시에 만들면 한쪽이 실패한다. 실제로 존재하면 정상이다.
            try:
                await self._client.get_collection(collection_name=name)
            except Exception as verify_error:
                raise RuntimeError(f"failed to ensure qdrant collection: {name}") from verify_error
            logger.debug("qdrant collection already existed", extra={"collection": name})
        else:
            logger.info("qdrant collection created", extra={"collection": name})
        self._known.add(name)

    async def upsert_chunks(
        self, *, post_id: str, model_name: str, chunks: list[Chunk], payload: dict[str, Any]
    ) -> UpsertResult:
        if not chunks:
            return UpsertResult(0, self._base, 0)

        dimension = len(chunks[0].vector)
        if dimension <= 0:
            raise ValueError("embedding vector dimension must be > 0")
        if any(len(chunk.vector) != dimension for chunk in chunks):
            raise ValueError("inconsistent vector dimensions within one post")

        collection = self.collection_for(model_name, dimension)
        await self._ensure_collection(collection, dimension)

        points = [
            PointStruct(
                id=str(
                    uuid.uuid5(
                        _POINT_NAMESPACE,
                        f"{post_id}:{model_name}:{dimension}:{chunk.chunk_index}",
                    )
                ),
                vector=chunk.vector,
                payload={
                    **payload,
                    "post_id": post_id,
                    "chunk_index": chunk.chunk_index,
                    "chunk_text": chunk.chunk_text,
                    "model_name": model_name,
                },
            )
            for chunk in chunks
        ]
        await self._client.upsert(collection_name=collection, points=points)
        logger.info(
            "vectors upserted",
            extra={"post_id": post_id, "chunks": len(points), "collection": collection},
        )
        return UpsertResult(len(points), collection, dimension)

    async def search(
        self,
        query_vector: list[float],
        model_name: str,
        *,
        limit: int = 5,
        score_threshold: float = 0.5,
    ) -> list[SearchHit]:
        """유사 청크를 찾는다.

        검색 실패는 빈 결과로 낮춘다. 벡터 검색이 안 되더라도 챗봇이 "찾지
        못했습니다"라고 답하는 편이 500을 내는 것보다 낫다.
        """
        if not query_vector:
            return []
        collection = self.collection_for(model_name, len(query_vector))
        try:
            response = await self._client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=limit,
                with_payload=True,
                score_threshold=score_threshold,
            )
        except Exception as exc:
            logger.warning(
                "qdrant search failed; degrading to empty",
                extra={"collection": collection, "reason": str(exc)[:200]},
            )
            return []
        self._known.add(collection)
        return [
            SearchHit(score=point.score, payload=dict(point.payload or {}))
            for point in response.points
        ]

    async def delete_posts(self, post_ids: list[str]) -> int:
        """포스트들의 청크를 모든 모델 컬렉션에서 지운다.

        모델을 바꾸면 컬렉션이 늘어나므로 prefix로 전부 훑는다. 일부가
        실패하면 예외를 던져 잡이 재시도하게 한다 — 벡터가 남으면 지워진
        포스트가 검색 결과에 계속 나온다.
        """
        if not post_ids:
            return 0
        prefix = f"{self._base}__"
        collections = [
            c.name
            for c in (await self._client.get_collections()).collections
            if c.name.startswith(prefix)
        ]
        selector = Filter(must=[FieldCondition(key="post_id", match=MatchAny(any=post_ids))])
        failed: list[str] = []
        for name in collections:
            try:
                await self._client.delete(collection_name=name, points_selector=selector)
            except Exception as exc:
                logger.warning(
                    "qdrant delete failed",
                    extra={"collection": name, "reason": str(exc)[:200]},
                )
                failed.append(name)
        if failed:
            raise RuntimeError("failed to delete vectors from: " + ", ".join(failed))
        return len(collections)
