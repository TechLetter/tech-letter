from __future__ import annotations

from datetime import datetime

from pymongo.database import Database

from app.repositories.interfaces import BlogRepositoryInterface
from common.models.blog import Blog, ListBlogsFilter


class BlogRepository(BlogRepositoryInterface):
    """blogs 컬렉션에 대한 MongoDB 접근 레이어.

    Go `repositories.BlogRepository` 와 동일한 책임을 갖는다.
    """

    def __init__(self, database: Database) -> None:
        """Mongo Database를 의존성으로 받고, blogs 컬렉션을 내부에서 선택한다."""

        self._db = database
        self._col = database["blogs"]

    def upsert_by_rss_url(self, blog: Blog) -> str:
        now = datetime.utcnow()
        if blog.created_at is None:
            blog.created_at = now
        blog.updated_at = now

        filter_doc = {"rss_url": blog.rss_url}
        update_doc = {
            "$setOnInsert": {"created_at": blog.created_at},
            "$set": {
                "updated_at": blog.updated_at,
                "name": blog.name,
                "url": blog.url,
                "rss_url": blog.rss_url,
                "blog_type": blog.blog_type,
            },
        }

        result = self._col.update_one(filter_doc, update_doc, upsert=True)
        # upsert 된 문서의 ID 가 있으면 반환하고, 없으면 기존 문서의 ID 를 다시 조회한다.
        if result.upserted_id is not None:
            return str(result.upserted_id)

        existing = self._col.find_one(filter_doc, {"_id": 1})
        if not existing:
            raise RuntimeError(
                "upsert_by_rss_url failed: document not found after update"
            )
        return str(existing["_id"])

    def get_by_rss_url(self, rss_url: str) -> Blog | None:
        doc = self._col.find_one({"rss_url": rss_url})
        if not doc:
            return None
        data = dict(doc)
        _id = data.pop("_id", None)
        if _id is not None:
            data["id"] = str(_id)
        return Blog.model_validate(data)

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
        for doc in cursor:
            data = dict(doc)
            _id = data.pop("_id", None)
            if _id is not None:
                data["id"] = str(_id)
            items.append(Blog.model_validate(data))

        return items, total
