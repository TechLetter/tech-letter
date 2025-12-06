from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Bookmark(BaseModel):
    """유저가 북마크한 포스트 도메인 모델."""

    id: str | None = None
    user_code: str
    post_id: str
    created_at: datetime
