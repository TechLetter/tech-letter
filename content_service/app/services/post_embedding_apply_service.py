from __future__ import annotations

import logging
from datetime import datetime, timezone

from common.events.post import PostEmbeddingAppliedEvent
from common.models.post import EmbeddingMetadata, StatusFlags

from ..repositories.interfaces import PostRepositoryInterface


logger = logging.getLogger(__name__)


class PostEmbeddingApplyService:
    def __init__(self, post_repository: PostRepositoryInterface) -> None:
        self._post_repository = post_repository

    def apply(self, event: PostEmbeddingAppliedEvent) -> None:
        post_id = event.post_id
        if not post_id:
            logger.error("PostEmbeddingAppliedEvent has empty post_id: %r", event)
            return

        try:
            post = self._post_repository.find_by_id(post_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to load post for PostEmbeddingAppliedEvent post_id=%s", post_id
            )
            raise

        if post is None:
            logger.warning(
                "post not found for PostEmbeddingAppliedEvent post_id=%s", post_id
            )
            return

        try:
            embedded_at = datetime.fromisoformat(event.timestamp)
        except Exception:  # noqa: BLE001
            logger.exception(
                "invalid timestamp on PostEmbeddingAppliedEvent id=%s timestamp=%r, falling back to now",
                event.id,
                event.timestamp,
            )
            embedded_at = datetime.now(timezone.utc)

        embedding = EmbeddingMetadata(
            model_name=event.model_name or None,
            collection_name=event.collection_name or None,
            vector_dimension=(
                event.vector_dimension if event.vector_dimension > 0 else None
            ),
            chunk_count=event.chunk_count,
            embedded_at=embedded_at,
        )

        status = post.status if post.status is not None else StatusFlags()
        status.embedded = True

        updates = {
            "embedding": embedding.model_dump(by_alias=True),
            "status": status.model_dump(by_alias=True),
        }

        try:
            self._post_repository.update_fields(post_id, updates)
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to update post embedding status for post_id=%s event_id=%s",
                post_id,
                event.id,
            )
            raise

        logger.info(
            "applied PostEmbeddingAppliedEvent id=%s to post_id=%s (model=%s chunks=%s)",
            event.id,
            post_id,
            event.model_name,
            event.chunk_count,
        )
