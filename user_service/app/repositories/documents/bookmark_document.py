from __future__ import annotations

from datetime import datetime

from common.mongo.types import BaseDocument, from_object_id
from ...models.bookmark import Bookmark


class BookmarkDocument(BaseDocument):
    """MongoDB bookmarks 컬렉션 도큐먼트 모델."""

    user_code: str
    post_id: str

    @classmethod
    def from_domain(cls, bookmark: Bookmark) -> "BookmarkDocument":
        data = {
            "user_code": bookmark.user_code,
            "post_id": bookmark.post_id,
            "created_at": bookmark.created_at,
            "updated_at": bookmark.created_at,
        }
        return cls.model_validate(data)

    def to_domain(self) -> Bookmark:
        created_at: datetime = (
            self.created_at
            if isinstance(self.created_at, datetime)
            else datetime.fromisoformat(str(self.created_at))
        )
        return Bookmark(
            id=from_object_id(self.id),
            user_code=self.user_code,
            post_id=self.post_id,
            created_at=created_at,
        )
