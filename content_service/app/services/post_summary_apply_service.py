from __future__ import annotations

import logging
from datetime import datetime, timezone

from common.events.post import PostSummarizedEvent
from common.models.post import AISummary, StatusFlags

from ..repositories.interfaces import PostRepositoryInterface


logger = logging.getLogger(__name__)


class PostSummaryApplyService:
    """PostSummarizedEvent 를 받아 MongoDB Post 문서에 요약 정보를 반영하는 서비스."""

    def __init__(self, post_repository: PostRepositoryInterface) -> None:
        self._post_repository = post_repository

    def apply(self, event: PostSummarizedEvent) -> None:
        """요약 완료 이벤트를 받아 Post 문서에 요약/플래그를 반영한다."""

        post_id = event.post_id
        if not post_id:
            logger.error("PostSummarizedEvent has empty post_id: %r", event)
            return

        try:
            post = self._post_repository.find_by_id(post_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to load post for PostSummarizedEvent post_id=%s", post_id
            )
            raise

        if post is None:
            logger.warning("post not found for PostSummarizedEvent post_id=%s", post_id)
            return

        try:
            generated_at = datetime.fromisoformat(event.timestamp)
        except Exception:  # noqa: BLE001
            logger.exception(
                "invalid timestamp on PostSummarizedEvent id=%s timestamp=%r, falling back to now",
                event.id,
                event.timestamp,
            )
            generated_at = datetime.now(timezone.utc)

        summary = AISummary(
            categories=event.categories,
            tags=event.tags,
            summary=event.summary or "",
            model_name=event.model_name or "",
            generated_at=generated_at,
        )

        status = StatusFlags(ai_summarized=True)

        updates = {
            "plain_text": event.plain_text or "",
            "thumbnail_url": event.thumbnail_url or "",
            "aisummary": summary.model_dump(by_alias=True),
            "status": status.model_dump(by_alias=True),
        }

        try:
            self._post_repository.update_fields(post_id, updates)
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to update post with summary for post_id=%s id=%s",
                post_id,
                event.id,
            )
            raise

        logger.info(
            "applied PostSummarizedEvent id=%s to post_id=%s (model=%s)",
            event.id,
            post_id,
            event.model_name,
        )
