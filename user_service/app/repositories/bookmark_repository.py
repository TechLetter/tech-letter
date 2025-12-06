from __future__ import annotations

from datetime import datetime, timezone

from pymongo.database import Database

from common.mongo.types import from_object_id, to_object_id

from .documents.bookmark_document import BookmarkDocument
from .interfaces import BookmarkRepositoryInterface
from ..models.bookmark import Bookmark


class BookmarkRepository(BookmarkRepositoryInterface):
    """bookmarks 컬렉션에 대한 MongoDB 접근 레이어."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._col = database["bookmarks"]

    def create(self, user_code: str, post_id: str) -> Bookmark:
        now = datetime.now(timezone.utc)
        doc = BookmarkDocument.from_domain(
            Bookmark(user_code=user_code, post_id=post_id, created_at=now)
        )
        payload = doc.to_mongo_record()
        result = self._col.update_one(
            {"user_code": user_code, "post_id": post_id},
            {"$setOnInsert": payload},
            upsert=True,
        )
        # 이미 존재하던 경우에도 일단 현재 값을 다시 읽어온다.
        found = self._col.find_one({"user_code": user_code, "post_id": post_id})
        assert found is not None
        return BookmarkDocument.model_validate(found).to_domain()

    def delete(self, user_code: str, post_id: str) -> bool:
        result = self._col.delete_one({"user_code": user_code, "post_id": post_id})
        return result.deleted_count > 0

    def list_by_user(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list[Bookmark], int]:
        if page <= 0:
            page = 1
        if page_size <= 0 or page_size > 100:
            page_size = 20

        skip = (page - 1) * page_size

        total = self._col.count_documents({"user_code": user_code})
        cursor = self._col.find(
            {"user_code": user_code},
            sort=[("created_at", -1), ("_id", -1)],
            skip=skip,
            limit=page_size,
        )

        items: list[Bookmark] = []
        for raw in cursor:
            items.append(BookmarkDocument.model_validate(raw).to_domain())

        return items, total

    def list_post_ids_for_user(self, user_code: str, post_ids: list[str]) -> list[str]:
        if not post_ids:
            return []

        cursor = self._col.find(
            {"user_code": user_code, "post_id": {"$in": post_ids}},
            {"post_id": 1},
        )
        ids: list[str] = []
        for raw in cursor:
            value = raw.get("post_id")
            if value is not None:
                ids.append(str(value))
        return ids
