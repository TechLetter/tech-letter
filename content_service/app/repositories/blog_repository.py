from __future__ import annotations

from datetime import datetime, timezone

from pymongo.database import Database

from .documents.blog_document import BlogDocument
from .interfaces import BlogRepositoryInterface
from common.models.blog import Blog, ListBlogsFilter
from common.mongo.types import from_object_id


class BlogRepository(BlogRepositoryInterface):
    """blogs 컬렉션에 대한 MongoDB 접근 레이어.

    Go `repositories.BlogRepository` 와 동일한 책임을 갖는다.
    """

    def __init__(self, database: Database) -> None:
        """Mongo Database를 의존성으로 받고, blogs 컬렉션을 내부에서 선택한다."""

        self._db = database
        self._col = database["blogs"]

    def upsert_by_rss_url(self, blog: Blog) -> str:
        now = datetime.now(timezone.utc)
        blog.updated_at = now

        # 도메인 -> Document 변환을 통해 Mongo 스키마를 일관되게 유지한다.
        doc = BlogDocument.from_domain(blog)
        # BaseDocument.to_mongo_record() 를 통해 Mongo-safe 직렬화를 일관되게 사용한다.
        payload = doc.to_mongo_record()

        filter_doc = {"rss_url": payload["rss_url"]}
        update_doc = {
            "$setOnInsert": {"created_at": payload["created_at"]},
            "$set": {
                "updated_at": payload["updated_at"],
                "name": payload["name"],
                "url": payload["url"],
                "rss_url": payload["rss_url"],
                "blog_type": payload["blog_type"],
            },
        }

        result = self._col.update_one(filter_doc, update_doc, upsert=True)
        if result.upserted_id is not None:
            return str(result.upserted_id)

        existing = self._col.find_one(filter_doc, {"_id": 1})
        if not existing:
            raise RuntimeError(
                "upsert_by_rss_url failed: document not found after update"
            )
        return str(existing["_id"])

    def get_by_rss_url(self, rss_url: str) -> Blog | None:
        raw = self._col.find_one({"rss_url": rss_url})
        if not raw:
            return None

        doc = BlogDocument.model_validate(raw)
        return Blog(
            id=from_object_id(doc.id),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            name=doc.name,
            url=doc.url,
            rss_url=doc.rss_url,
            blog_type=doc.blog_type,
        )

    def list(self, flt: ListBlogsFilter) -> tuple[list[Blog], int]:
        page = flt.page if flt.page > 0 else 1
        page_size = flt.page_size
        if page_size <= 0 or page_size > 100:
            page_size = 20

        skip = (page - 1) * page_size

        filter_doc: dict = {}
        total = self._col.count_documents(filter_doc)

        cursor = self._col.find(
            filter_doc,
            sort=[("name", 1)],
            skip=skip,
            limit=page_size,
        )

        items: list[Blog] = []
        for raw in cursor:
            doc = BlogDocument.model_validate(raw)
            items.append(
                Blog(
                    id=from_object_id(doc.id),
                    created_at=doc.created_at,
                    updated_at=doc.updated_at,
                    name=doc.name,
                    url=doc.url,
                    rss_url=doc.rss_url,
                    blog_type=doc.blog_type,
                )
            )

        return items, total
