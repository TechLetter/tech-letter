from __future__ import annotations

from datetime import datetime, timezone

from pymongo import ASCENDING, IndexModel
from pymongo.database import Database

from .documents.blog_document import BlogDocument
from .interfaces import BlogRepositoryInterface
from common.models.blog import Blog, ListBlogsFilter
from common.mongo.types import from_object_id, to_object_id


class BlogRepository(BlogRepositoryInterface):
    """blogs 컬렉션에 대한 MongoDB 접근 레이어.

    Go `repositories.BlogRepository` 와 동일한 책임을 갖는다.
    """

    def __init__(self, database: Database) -> None:
        """Mongo Database를 의존성으로 받고, blogs 컬렉션을 내부에서 선택한다."""

        self._db = database
        self._col = database["blogs"]
        self._col.create_indexes(
            [
                IndexModel(
                    [("rss_url", ASCENDING)],
                    name="uniq_rss_url",
                    unique=True,
                ),
                IndexModel([("name", ASCENDING)], name="idx_blog_name"),
                IndexModel([("is_active", ASCENDING)], name="idx_blog_is_active"),
            ]
        )

    @staticmethod
    def _from_document(raw: dict) -> Blog:
        doc = BlogDocument.model_validate(raw)
        return Blog(
            id=from_object_id(doc.id),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            name=doc.name,
            url=doc.url,
            rss_url=doc.rss_url,
            blog_type=doc.blog_type,
            is_active=doc.is_active,
            last_fetched_at=doc.last_fetched_at,
            last_fetch_error=doc.last_fetch_error,
        )

    def create(self, blog: Blog) -> str:
        now = datetime.now(timezone.utc)
        blog.created_at = now
        blog.updated_at = now

        doc = BlogDocument.from_domain(blog)
        payload = doc.to_mongo_record()
        result = self._col.insert_one(payload)
        return str(result.inserted_id)

    def update(self, id_value: str, blog: Blog) -> bool:
        now = datetime.now(timezone.utc)
        doc = BlogDocument.from_domain(blog)
        payload = doc.to_mongo_record()
        update_doc = {
            "updated_at": now,
            "name": payload["name"],
            "url": payload["url"],
            "rss_url": payload["rss_url"],
            "blog_type": payload["blog_type"],
            "is_active": payload.get("is_active", True),
        }
        result = self._col.update_one(
            {"_id": to_object_id(id_value)},
            {"$set": update_doc},
        )
        return result.matched_count > 0

    def delete_by_id(self, id_value: str) -> bool:
        result = self._col.delete_one({"_id": to_object_id(id_value)})
        return result.deleted_count > 0

    def get_by_rss_url(self, rss_url: str) -> Blog | None:
        raw = self._col.find_one({"rss_url": rss_url})
        if not raw:
            return None

        return self._from_document(raw)

    def get_by_url(self, url: str) -> Blog | None:
        raw = self._col.find_one({"url": url})
        if not raw:
            return None

        return self._from_document(raw)

    def find_by_id(self, id_value: str) -> Blog | None:
        raw = self._col.find_one({"_id": to_object_id(id_value)})
        if not raw:
            return None
        return self._from_document(raw)

    def list(self, flt: ListBlogsFilter) -> tuple[list[Blog], int]:
        page = flt.page if flt.page > 0 else 1
        page_size = flt.page_size
        if page_size <= 0 or page_size > 100:
            page_size = 20

        skip = (page - 1) * page_size

        filter_doc: dict = {}
        if not flt.include_inactive:
            filter_doc["is_active"] = {"$ne": False}

        total = self._col.count_documents(filter_doc)

        cursor = self._col.find(
            filter_doc,
            sort=[("name", 1)],
            skip=skip,
            limit=page_size,
        )

        items: list[Blog] = []
        for raw in cursor:
            items.append(self._from_document(raw))

        return items, total

    def list_active_sources(self) -> list[Blog]:
        cursor = self._col.find(
            {"is_active": {"$ne": False}},
            sort=[("name", 1)],
        )
        return [self._from_document(raw) for raw in cursor]

    def update_fetch_result(self, id_value: str, error: str | None) -> None:
        now = datetime.now(timezone.utc)
        updates: dict = {
            "updated_at": now,
            "last_fetched_at": now,
            "last_fetch_error": error,
        }
        self._col.update_one(
            {"_id": to_object_id(id_value)},
            {"$set": updates},
        )
