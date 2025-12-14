from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from pymongo import UpdateOne
from pymongo.database import Database


logger = logging.getLogger(__name__)

CACHE_COLLECTION = "embedding_cache"


def _compute_cache_key(text: str, model_name: str) -> str:
    """텍스트와 모델 이름으로 캐시 키를 생성한다."""
    content = f"{model_name}:{text}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """MongoDB 기반 임베딩 캐시.

    텍스트+모델명을 키로 임베딩 벡터를 캐싱하여 중복 호출을 방지한다.
    """

    def __init__(self, db: Database) -> None:
        self._collection = db[CACHE_COLLECTION]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """캐시 키 인덱스를 생성한다."""
        self._collection.create_index("cache_key", unique=True)
        self._collection.create_index("created_at")

    def get(self, text: str, model_name: str) -> list[float] | None:
        """캐시에서 임베딩 벡터를 조회한다."""
        cache_key = _compute_cache_key(text, model_name)
        doc = self._collection.find_one(
            {"cache_key": cache_key},
            projection={"_id": 0, "vector": 1},
        )

        if doc is None:
            logger.debug("cache miss for key=%s", cache_key[:16])
            return None

        logger.debug("cache hit for key=%s", cache_key[:16])
        return doc.get("vector")

    def set(self, text: str, model_name: str, vector: list[float]) -> None:
        """임베딩 벡터를 캐시에 저장한다."""
        cache_key = _compute_cache_key(text, model_name)
        now = datetime.now(timezone.utc)

        doc: dict[str, Any] = {
            "cache_key": cache_key,
            "model_name": model_name,
            "vector": vector,
            "text_length": len(text),
            "created_at": now,
        }

        self._collection.update_one(
            {"cache_key": cache_key},
            {"$set": doc},
            upsert=True,
        )
        logger.debug("cached embedding for key=%s", cache_key[:16])

    def get_many(
        self, texts: list[str], model_name: str
    ) -> dict[int, list[float] | None]:
        """여러 텍스트에 대한 캐시를 조회한다.

        Returns:
            인덱스를 키로, 캐시된 벡터(또는 None)를 값으로 하는 딕셔너리
        """
        if not texts:
            return {}

        results: dict[int, list[float] | None] = {}
        cache_keys = [_compute_cache_key(t, model_name) for t in texts]

        docs = self._collection.find(
            {"cache_key": {"$in": cache_keys}},
            projection={"_id": 0, "cache_key": 1, "vector": 1},
        )
        key_to_vector = {doc["cache_key"]: doc.get("vector") for doc in docs}

        for idx, cache_key in enumerate(cache_keys):
            results[idx] = key_to_vector.get(cache_key)

        hit_count = sum(1 for v in results.values() if v is not None)
        logger.debug("cache lookup: %d hits / %d total", hit_count, len(texts))
        return results

    def set_many(
        self, texts: list[str], model_name: str, vectors: list[list[float]]
    ) -> None:
        """여러 임베딩 벡터를 캐시에 저장한다."""
        if not texts:
            return

        if len(texts) != len(vectors):
            raise RuntimeError(
                "embedding cache set_many size mismatch: "
                f"texts={len(texts)} vectors={len(vectors)} model={model_name}"
            )

        now = datetime.now(timezone.utc)
        operations = []

        for text, vector in zip(texts, vectors):
            cache_key = _compute_cache_key(text, model_name)
            doc: dict[str, Any] = {
                "cache_key": cache_key,
                "model_name": model_name,
                "vector": vector,
                "text_length": len(text),
                "created_at": now,
            }
            operations.append(
                UpdateOne({"cache_key": cache_key}, {"$set": doc}, upsert=True)
            )

        if operations:
            self._collection.bulk_write(operations, ordered=False)
            logger.debug("cached %d embeddings", len(operations))
