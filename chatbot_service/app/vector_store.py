from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, cast

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from common.events.post import PostEmbedResponseEvent
from common.llm.utils import normalize_model_name

from .config import QdrantConfig


logger = logging.getLogger(__name__)


class _QdrantCollectionDescription(Protocol):
    name: str


class _QdrantCollectionsResponse(Protocol):
    collections: list[_QdrantCollectionDescription]


class _QdrantScoredPoint(Protocol):
    score: float
    payload: dict[str, Any] | None


class _QdrantClient(Protocol):
    def get_collections(
        self, *args: Any, **kwargs: Any
    ) -> _QdrantCollectionsResponse: ...

    def create_collection(self, *args: Any, **kwargs: Any) -> Any: ...

    def get_collection(self, *args: Any, **kwargs: Any) -> Any: ...

    def upsert(self, *args: Any, **kwargs: Any) -> Any: ...

    def search(self, *args: Any, **kwargs: Any) -> list[_QdrantScoredPoint]: ...

    def delete(self, *args: Any, **kwargs: Any) -> Any: ...


class VectorStore:
    """Qdrant Vector DB 클라이언트 래퍼."""

    def __init__(self, config: QdrantConfig) -> None:
        self._client = cast(
            _QdrantClient,
            QdrantClient(host=config.host, port=config.port),
        )
        self._base_collection_name = config.collection_name
        self._known_collections: set[str] = set()

    def _search_points(
        self,
        *,
        collection_name: str,
        query_vector: list[float],
        limit: int,
    ) -> list[_QdrantScoredPoint]:
        """qdrant-client 버전별 검색 API 차이를 흡수한다.

        - 일부 버전/클라이언트에서는 `search`가 없고 `search_points` 또는 `query_points`만 제공한다.
        - 반환 타입도 버전에 따라 list 또는 response object(points=...) 형태가 될 수 있다.
        """

        search_method = getattr(self._client, "search", None)
        if callable(search_method):
            raw = search_method(
                collection_name,
                query_vector,
                limit=limit,
                with_payload=True,
            )
            if isinstance(raw, list):
                return cast(list[_QdrantScoredPoint], raw)
            points = getattr(raw, "points", None)
            if isinstance(points, list):
                return cast(list[_QdrantScoredPoint], points)

        search_points_method = getattr(self._client, "search_points", None)
        if callable(search_points_method):
            raw = search_points_method(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
            )
            if isinstance(raw, list):
                return cast(list[_QdrantScoredPoint], raw)
            points = getattr(raw, "points", None)
            if isinstance(points, list):
                return cast(list[_QdrantScoredPoint], points)

        query_points_method = getattr(self._client, "query_points", None)
        if callable(query_points_method):
            raw = query_points_method(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
            )
            points = getattr(raw, "points", None)
            if isinstance(points, list):
                return cast(list[_QdrantScoredPoint], points)

        raise RuntimeError(
            "qdrant client does not support search (expected one of: search, search_points, query_points)"
        )

    def _collection_model_key(self, model_name: str) -> str:
        normalized_model_name = normalize_model_name(model_name)
        key = normalized_model_name.strip().lower()
        key = re.sub(r"[^a-z0-9_\-]+", "_", key)
        key = re.sub(r"_+", "_", key).strip("_")
        return key or "unknown"

    def _collection_name_for(self, *, model_name: str, vector_dimension: int) -> str:
        model_key = self._collection_model_key(model_name)
        return f"{self._base_collection_name}__{model_key}__{vector_dimension}"

    def _ensure_collection(
        self, *, collection_name: str, vector_dimension: int
    ) -> None:
        if collection_name in self._known_collections:
            return

        try:
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_dimension,
                    distance=Distance.COSINE,
                ),
            )
        except Exception as create_error:
            # 캐시는 힌트로만 사용하고, 최종 판단은 서버 상태(존재 여부)로 한다.
            # 멀티 인스턴스 레이스로 인해 create가 실패하더라도, 실제로 컬렉션이 이미 존재하면 정상으로 간주.
            try:
                self._client.get_collection(collection_name=collection_name)
            except Exception as verify_error:
                raise RuntimeError(
                    f"failed to ensure qdrant collection: {collection_name}"
                ) from verify_error
            else:
                self._known_collections.add(collection_name)
                logger.info(
                    "qdrant collection already exists (create race): %s error=%s",
                    collection_name,
                    create_error,
                )
        else:
            self._known_collections.add(collection_name)
            logger.info("created qdrant collection: %s", collection_name)

    @dataclass(frozen=True, slots=True)
    class UpsertResult:
        chunk_count: int
        collection_name: str
        vector_dimension: int

    def upsert_post_embeddings(self, event: PostEmbedResponseEvent) -> UpsertResult:
        """PostEmbedResponseEvent의 청크들을 Vector DB에 upsert한다.

        Returns:
            upsert된 포인트 수
        """
        if not event.chunks:
            logger.warning("no chunks to upsert for post_id=%s", event.post_id)
            return self.UpsertResult(
                chunk_count=0,
                collection_name=self._base_collection_name,
                vector_dimension=0,
            )

        if not event.model_name:
            raise RuntimeError("PostEmbedResponseEvent.model_name is required")

        first_vector = event.chunks[0].vector
        vector_dimension = len(first_vector)
        if vector_dimension <= 0:
            raise RuntimeError("embedding vector dimension must be > 0")

        for chunk in event.chunks:
            if len(chunk.vector) != vector_dimension:
                raise RuntimeError(
                    "inconsistent embedding vector dimensions within the same event",
                )

        target_collection = self._collection_name_for(
            model_name=event.model_name,
            vector_dimension=vector_dimension,
        )
        self._ensure_collection(
            collection_name=target_collection,
            vector_dimension=vector_dimension,
        )

        points: list[PointStruct] = []
        for chunk in event.chunks:
            stable_id = f"{event.post_id}:{event.model_name}:{vector_dimension}:{chunk.chunk_index}"
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_id))
            payload: dict[str, Any] = {
                "post_id": event.post_id,
                "title": event.title,
                "blog_name": event.blog_name,
                "link": event.link,
                "published_at": event.published_at,
                "categories": event.categories,
                "tags": event.tags,
                "chunk_index": chunk.chunk_index,
                "chunk_text": chunk.chunk_text,
                "model_name": event.model_name,
            }
            points.append(
                PointStruct(
                    id=point_id,
                    vector=chunk.vector,
                    payload=payload,
                )
            )

        self._client.upsert(
            collection_name=target_collection,
            points=points,
        )

        logger.info(
            "upserted %d chunks for post_id=%s title=%s",
            len(points),
            event.post_id,
            event.title,
        )
        return self.UpsertResult(
            chunk_count=len(points),
            collection_name=target_collection,
            vector_dimension=vector_dimension,
        )

    def search(
        self,
        query_vector: list[float],
        model_name: str,
        limit: int = 5,
        score_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """쿼리 벡터로 유사한 청크를 검색한다.

        Returns:
            검색 결과 리스트 (payload + score)
        """
        vector_dimension = len(query_vector)
        if vector_dimension <= 0:
            raise RuntimeError("query_vector dimension must be > 0")

        target_collection = self._collection_name_for(
            model_name=model_name,
            vector_dimension=vector_dimension,
        )

        try:
            results = self._search_points(
                collection_name=target_collection,
                query_vector=query_vector,
                limit=limit,
            )
        except Exception as search_error:
            # 운영 관점에서 search 실패는 사용자 응답을 깨지 않도록 empty로 degrade.
            logger.warning(
                "qdrant search failed; returning empty. collection=%s error=%s",
                target_collection,
                search_error,
            )
            return []
        else:
            # positive cache (성능 힌트): 성공한 컬렉션만 기억한다.
            self._known_collections.add(target_collection)

        search_results: list[dict[str, Any]] = []
        for hit in results:
            if hit.score < score_threshold:
                continue
            result = dict(hit.payload) if hit.payload else {}
            result["score"] = hit.score
            search_results.append(result)

        logger.debug("search returned %d results", len(search_results))
        return search_results

    def delete_by_post_id(self, post_id: str) -> None:
        """특정 post_id의 모든 청크를 삭제한다."""
        prefix = f"{self._base_collection_name}__"

        try:
            collections = self._client.get_collections().collections
        except Exception as list_error:
            logger.warning(
                "failed to list qdrant collections; skipping delete. post_id=%s error=%s",
                post_id,
                list_error,
            )
            return

        target_collections = [c.name for c in collections if c.name.startswith(prefix)]

        for collection_name in target_collections:
            try:
                self._client.delete(
                    collection_name=collection_name,
                    points_selector=Filter(
                        must=[
                            FieldCondition(
                                key="post_id",
                                match=MatchValue(value=post_id),
                            )
                        ]
                    ),
                )
            except Exception as delete_error:
                logger.warning(
                    "failed to delete points from qdrant collection. post_id=%s collection=%s error=%s",
                    post_id,
                    collection_name,
                    delete_error,
                )

        logger.info(
            "deleted chunks for post_id=%s collections=%d",
            post_id,
            len(target_collections),
        )
