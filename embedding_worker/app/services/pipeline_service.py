from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import cast

from common.eventbus.helpers import new_json_event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_POST_EMBEDDING
from common.events.post import (
    EmbeddingChunk,
    EventType,
    PostEmbeddingRequestedEvent,
    PostEmbedResponseEvent,
)

from ..cache import EmbeddingCache
from ..embedder import TextEmbedder


logger = logging.getLogger(__name__)


def handle_post_embedding_requested_event(
    requested: PostEmbeddingRequestedEvent,
    *,
    bus: KafkaEventBus,
    embedder: TextEmbedder,
    cache: EmbeddingCache,
) -> None:
    """PostEmbeddingRequestedEvent에 대한 임베딩 파이프라인을 처리한다.

    - 텍스트 청킹
    - 캐시 확인
    - 캐시 미스 시 임베딩 생성
    - 캐시 저장
    - PostEmbedResponseEvent 발행
    """

    logger.info(
        "handling PostEmbeddingRequestedEvent id=%s post_id=%s title=%s",
        requested.id,
        requested.post_id,
        requested.title,
    )

    # 1. 텍스트 청킹 (plain_text 사용)
    try:
        chunks = embedder.chunk_text(requested.plain_text)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to chunk text for PostEmbeddingRequestedEvent id=%s post_id=%s",
            requested.id,
            requested.post_id,
        )
        raise

    if not chunks:
        logger.warning(
            "no chunks generated for post_id=%s, skipping embedding",
            requested.post_id,
        )
        return

    logger.debug(
        "chunked text into %d chunks for post_id=%s", len(chunks), requested.post_id
    )

    # 2. 캐시 확인
    normalized_model_name = embedder.normalized_model_name
    try:
        cached_results: dict[int, list[float] | None] = cache.get_many(
            chunks, normalized_model_name
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to read embedding cache for post_id=%s (non-fatal)",
            requested.post_id,
        )
        cached_results = cast(
            dict[int, list[float] | None],
            {idx: None for idx in range(len(chunks))},
        )

    # 3. 캐시 미스인 청크들에 대해 임베딩 생성
    missing_indices = [idx for idx, vec in cached_results.items() if vec is None]

    if missing_indices:
        logger.debug(
            "cache miss for %d/%d chunks, generating embeddings",
            len(missing_indices),
            len(chunks),
        )

        missing_texts = [chunks[idx] for idx in missing_indices]

        try:
            new_vectors = embedder.embed_texts(missing_texts)
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to generate embeddings for PostEmbeddingRequestedEvent id=%s post_id=%s",
                requested.id,
                requested.post_id,
            )
            raise

        if len(new_vectors) != len(missing_texts):
            raise RuntimeError(
                "embedding result size mismatch: "
                f"expected={len(missing_texts)} actual={len(new_vectors)} "
                f"post_id={requested.post_id} model={normalized_model_name}"
            )

        # 4. 새로 생성된 임베딩을 캐시에 저장
        try:
            cache.set_many(missing_texts, normalized_model_name, new_vectors)
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to cache embeddings for post_id=%s (non-fatal)",
                requested.post_id,
            )

        # 결과 병합
        for idx, vector in zip(missing_indices, new_vectors):
            cached_results[idx] = vector
    else:
        logger.debug(
            "all %d chunks found in cache for post_id=%s",
            len(chunks),
            requested.post_id,
        )

    # 5. EmbeddingChunk 리스트 구성
    embedding_chunks: list[EmbeddingChunk] = []
    for idx in range(len(chunks)):
        vector = cached_results.get(idx)
        if vector is None:
            raise RuntimeError(
                f"missing vector for chunk_index={idx} post_id={requested.post_id} model={normalized_model_name}"
            )

        embedding_chunks.append(
            EmbeddingChunk(
                chunk_index=idx,
                chunk_text=chunks[idx],
                vector=vector,
            )
        )

    if not embedding_chunks:
        raise RuntimeError(
            f"no embedding chunks produced for post_id={requested.post_id} model={normalized_model_name}"
        )

    # 6. PostEmbedResponse 이벤트 구성 및 publish
    now = datetime.now(timezone.utc).isoformat()
    response_event_id = str(uuid.uuid4())
    response_event = PostEmbedResponseEvent(
        id=response_event_id,
        type=EventType.POST_EMBEDDING_RESPONSE,
        timestamp=now,
        source="embedding-worker",
        version="1.0",
        post_id=requested.post_id,
        title=requested.title,
        blog_name=requested.blog_name,
        link=requested.link,
        published_at=requested.published_at,
        categories=requested.categories,
        tags=requested.tags,
        chunks=embedding_chunks,
        model_name=normalized_model_name,
    )

    try:
        out_evt = new_json_event(
            payload=asdict(response_event),
            event_id=response_event_id,
        )
        bus.publish(TOPIC_POST_EMBEDDING.base, out_evt)
    except Exception:  # noqa: BLE001
        logger.exception(
            "failed to publish PostEmbedResponseEvent for request id=%s post_id=%s",
            requested.id,
            requested.post_id,
        )
        raise

    logger.info(
        "successfully processed PostEmbeddingRequestedEvent id=%s post_id=%s chunks=%d model=%s",
        requested.id,
        requested.post_id,
        len(embedding_chunks),
        normalized_model_name,
    )
