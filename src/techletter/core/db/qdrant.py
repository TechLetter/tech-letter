"""Qdrant 벡터 저장소.

컬렉션 이름 규칙은 **운영 데이터에 이미 박혀 있어** 바꿀 수 없다:
`{base}__{model_key}__{dim}` (예: `tech_letter_posts__gemini-embedding-001__3072`).

어휘(BM25) 색인은 `{base}__lexical`에 포스트당 포인트 하나로 둔다. 같은 prefix라
`delete_posts`가 청크와 함께 지운다.
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
    MatchValue,
    Modifier,
    PayloadSchemaType,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from techletter.core.errors import VectorStoreUnavailableError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.settings import QdrantSettings

__all__ = [
    "LEXICAL_VECTOR",
    "Chunk",
    "LexicalPoint",
    "SearchHit",
    "VectorStore",
    "collection_name_for",
    "normalize_model_name",
]

logger = get_logger(__name__)

_NON_SLUG = re.compile(r"[^a-z0-9_\-]+")
_REPEATED_UNDERSCORE = re.compile(r"_+")
# 포인트 id를 만드는 네임스페이스. 같은 (post, model, dim, index)면 항상 같은 id가
# 나와야 재임베딩이 중복 포인트를 쌓지 않고 덮어쓴다.
_POINT_NAMESPACE = uuid.NAMESPACE_URL
LEXICAL_VECTOR = "bm25"
_LEXICAL_SUFFIX = "lexical"
# 어휘 검색 필터(블로그·주제)와 삭제(post_id)에 쓰는 payload 인덱스.
_LEXICAL_INDEXED_FIELDS = ("post_id", "blog_id", "categories")


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
class LexicalPoint:
    """포스트 하나의 BM25 희소 벡터. 값 계산은 `techletter.search.lexical`이 한다."""

    post_id: str
    indices: list[int]
    values: list[float]
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
        # 컬렉션과 post_id 인덱스를 정합화한 것을 기억해 매번 확인하지 않는다.
        # 힌트일 뿐이라 틀려도 다음 프로세스가 다시 정합화할 수 있다.
        self._known: set[str] = set()

    async def close(self) -> None:
        await self._client.close()

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

        await self._ensure_keyword_index(name, "post_id")
        self._known.add(name)

    async def _ensure_keyword_index(self, name: str, field_name: str) -> None:
        try:
            await self._client.create_payload_index(
                collection_name=name,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:
            # Qdrant는 같은 인덱스를 다시 만들 때 400을 돌려준다. 이 경우는
            # 이미 원하는 상태이므로 정상 처리하되, 연결 장애는 숨기지 않는다.
            if not _is_existing_payload_index_error(exc):
                raise RuntimeError(f"failed to ensure qdrant payload index: {name}") from exc
            logger.debug(
                "qdrant payload index already existed",
                extra={"collection": name, "field": field_name},
            )

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

        # 재임베딩으로 청크 수가 줄면 이전 꼬리 청크가 남지 않도록 먼저 비운다.
        # 요약 잡 주기상 삭제와 재등록 사이의 짧은 검색 공백은 허용한다.
        selector = Filter(must=[FieldCondition(key="post_id", match=MatchValue(value=post_id))])
        await self._client.delete(collection_name=collection, points_selector=selector)

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

        컬렉션이 아직 없는 신규 환경은 빈 결과로 낮춘다. 그 밖의 검색 장애는
        호출자가 장애를 구분해 처리할 수 있도록 예외로 올린다.
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
            if _is_collection_not_found_error(exc):
                logger.warning(
                    "qdrant collection not found; degrading to empty",
                    extra={"collection": collection},
                )
                return []
            raise VectorStoreUnavailableError(
                f"qdrant search failed for collection: {collection}"
            ) from exc
        return [
            SearchHit(score=point.score, payload=dict(point.payload or {}))
            for point in response.points
        ]

    # ── 어휘(BM25) 색인 ────────────────────────────────────────────
    @property
    def lexical_collection(self) -> str:
        return f"{self._base}__{_LEXICAL_SUFFIX}"

    async def _ensure_lexical_collection(self) -> None:
        name = self.lexical_collection
        if name in self._known:
            return
        try:
            await self._client.create_collection(
                collection_name=name,
                vectors_config={},
                # IDF는 Qdrant가 컬렉션 통계로 질의 때 곱한다. 문서 수가 늘어도
                # 이미 넣은 포인트를 다시 계산할 필요가 없다.
                sparse_vectors_config={LEXICAL_VECTOR: SparseVectorParams(modifier=Modifier.IDF)},
            )
        except Exception:
            try:
                await self._client.get_collection(collection_name=name)
            except Exception as verify_error:
                raise RuntimeError(f"failed to ensure qdrant collection: {name}") from verify_error
        else:
            logger.info("qdrant collection created", extra={"collection": name})
        for field_name in _LEXICAL_INDEXED_FIELDS:
            await self._ensure_keyword_index(name, field_name)
        self._known.add(name)

    async def upsert_lexical(self, points: list[LexicalPoint]) -> int:
        """포스트당 포인트 하나. id가 post_id로 정해져 다시 넣으면 덮어쓴다."""
        if not points:
            return 0
        await self._ensure_lexical_collection()
        await self._client.upsert(
            collection_name=self.lexical_collection,
            points=[
                PointStruct(
                    id=lexical_point_id(point.post_id),
                    vector={
                        LEXICAL_VECTOR: SparseVector(indices=point.indices, values=point.values)
                    },
                    payload={**point.payload, "post_id": point.post_id},
                )
                for point in points
            ],
        )
        return len(points)

    async def search_lexical(
        self,
        indices: list[int],
        *,
        limit: int,
        blog_id: str | None = None,
        categories: list[str] | None = None,
    ) -> list[SearchHit]:
        """질의 토큰마다 가중치 1로 찾는다. 점수는 Σ IDF × 문서 쪽 BM25 tf 항이다.

        색인이 아직 없는 환경은 빈 결과로 낮춘다. 그 밖의 장애는 예외로 올린다.
        """
        if not indices:
            return []
        conditions: list[Any] = []
        if blog_id:
            conditions.append(FieldCondition(key="blog_id", match=MatchValue(value=blog_id)))
        if categories:
            conditions.append(FieldCondition(key="categories", match=MatchAny(any=categories)))
        collection = self.lexical_collection
        try:
            response = await self._client.query_points(
                collection_name=collection,
                query=SparseVector(indices=indices, values=[1.0] * len(indices)),
                using=LEXICAL_VECTOR,
                query_filter=Filter(must=conditions) if conditions else None,
                limit=limit,
                with_payload=True,
            )
        except Exception as exc:
            if _is_collection_not_found_error(exc):
                logger.warning(
                    "qdrant collection not found; degrading to empty",
                    extra={"collection": collection},
                )
                return []
            raise VectorStoreUnavailableError(
                f"qdrant search failed for collection: {collection}"
            ) from exc
        return [
            SearchHit(score=point.score, payload=dict(point.payload or {}))
            for point in response.points
        ]

    async def delete_posts(self, post_ids: list[str]) -> int:
        """포스트들의 청크와 어휘 색인을 모든 컬렉션에서 지운다.

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


def lexical_point_id(post_id: str) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{post_id}:{_LEXICAL_SUFFIX}"))


def _is_collection_not_found_error(exc: Exception) -> bool:
    """Qdrant의 컬렉션 미존재 응답만 신규 환경으로 취급한다."""
    return getattr(exc, "status_code", None) == 404


def _is_existing_payload_index_error(exc: Exception) -> bool:
    """이미 생성된 payload 인덱스를 다시 만드는 Qdrant 응답인지 판별한다."""
    return (
        getattr(exc, "status_code", None) == 400
        and "payload index" in str(exc).lower()
        and "already exists" in str(exc).lower()
    )
