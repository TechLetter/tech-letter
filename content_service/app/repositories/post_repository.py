from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Iterable

from pymongo import IndexModel, ASCENDING, DESCENDING
from pymongo.database import Database

from .documents.post_document import PostDocument
from .interfaces import PostRepositoryInterface, TagCountRow, TagSeriesRow
from common.models.post import ListPostsFilter, Post
from common.mongo.types import from_object_id, to_object_id


class PostRepository(PostRepositoryInterface):
    """posts 컬렉션에 대한 MongoDB 접근 레이어.

    Go `repositories.PostRepository` 와 동일한 책임을 갖는다.
    """

    def __init__(self, database: Database) -> None:
        """Mongo Database를 의존성으로 받고, posts 컬렉션을 내부에서 선택한다."""

        self._db = database
        self._col = database["posts"]
        self._col.create_indexes(
            [
                IndexModel(
                    [("published_at", DESCENDING), ("_id", DESCENDING)],
                    name="idx_published_at_id_desc",
                ),
                IndexModel(
                    [("aisummary.categories", ASCENDING)], name="idx_categories"
                ),
                IndexModel([("aisummary.tags", ASCENDING)], name="idx_tags"),
                IndexModel(
                    [("aisummary.tags", ASCENDING), ("published_at", DESCENDING)],
                    name="idx_tags_published_at",
                ),
                IndexModel(
                    [("aisummary.categories", ASCENDING), ("published_at", DESCENDING)],
                    name="idx_categories_published_at",
                ),
                IndexModel([("link", ASCENDING)], name="uniq_link", unique=True),
            ]
        )

    # --- helpers -----------------------------------------------------------------
    @staticmethod
    def _to_document(post: Post) -> dict:
        doc = PostDocument.from_domain(post)

        # BaseDocument.to_mongo_record() 를 통해 Mongo-safe 직렬화를 일관되게 사용한다.
        return doc.to_mongo_record()

    @staticmethod
    def _from_document(doc: dict) -> Post:
        document = PostDocument.model_validate(doc)

        return Post(
            id=from_object_id(document.id),
            created_at=document.created_at,
            updated_at=document.updated_at,
            status=document.status,
            view_count=document.view_count,
            blog_id=str(document.blog_id),
            blog_name=document.blog_name,
            title=document.title,
            link=document.link,
            published_at=document.published_at,
            thumbnail_url=document.thumbnail_url,
            aisummary=document.aisummary,
            embedding=document.embedding,
        )

    # --- commands ----------------------------------------------------------------
    def is_exist_by_link(self, link: str) -> bool:
        """링크로 포스트 존재 여부를 확인한다."""

        found = self._col.find_one({"link": link}, {"_id": 1})
        return found is not None

    def insert(self, post: Post) -> str:
        """새 포스트를 삽입하고 생성된 ID 를 반환한다."""

        now = datetime.now(timezone.utc)
        post.updated_at = now

        doc = self._to_document(post)
        result = self._col.insert_one(doc)
        inserted_id = result.inserted_id
        if inserted_id is None:
            raise RuntimeError("insert failed: inserted_id is None (possible null _id)")
        return str(inserted_id)

    def find_by_link(self, link: str) -> Post | None:
        doc = self._col.find_one({"link": link})
        if not doc:
            return None
        return self._from_document(doc)

    def list(self, flt: ListPostsFilter) -> tuple[list[Post], int]:
        """필터/페이지네이션 기준으로 포스트 목록과 총 개수를 반환한다."""

        filter_doc: dict = {}

        def _to_regex_in(values: Iterable[str]) -> list[re.Pattern]:
            arr: list[re.Pattern] = []
            for v in values:
                v = v.strip()
                if not v:
                    continue
                arr.append(re.compile(f"^{v}$", re.IGNORECASE))
            return arr

        cats_regex = _to_regex_in(flt.categories)
        tags_regex = _to_regex_in(flt.tags)

        if cats_regex and tags_regex:
            filter_doc["$or"] = [
                {"aisummary.categories": {"$in": cats_regex}},
                {"aisummary.tags": {"$in": tags_regex}},
            ]
        elif cats_regex:
            filter_doc["aisummary.categories"] = {"$in": cats_regex}
        elif tags_regex:
            filter_doc["aisummary.tags"] = {"$in": tags_regex}

        if flt.blog_id:
            filter_doc["blog_id"] = to_object_id(flt.blog_id)
        if flt.blog_name:
            filter_doc["blog_name"] = {"$regex": f"^{flt.blog_name}$", "$options": "i"}
        if flt.published_from or flt.published_to:
            published_range: dict[str, datetime] = {}
            if flt.published_from:
                published_range["$gte"] = flt.published_from
            if flt.published_to:
                published_range["$lte"] = flt.published_to
            filter_doc["published_at"] = published_range

        # Status 필터링: false 조회 시 필드가 없는 경우도 포함
        if flt.status_ai_summarized is not None:
            if flt.status_ai_summarized:
                filter_doc["status.ai_summarized"] = True
            else:
                # false이거나 필드가 없는 경우 모두 매칭
                filter_doc["$and"] = filter_doc.get("$and", []) + [
                    {
                        "$or": [
                            {"status.ai_summarized": False},
                            {"status.ai_summarized": {"$exists": False}},
                        ]
                    }
                ]
        if flt.status_embedded is not None:
            if flt.status_embedded:
                filter_doc["status.embedded"] = True
            else:
                filter_doc["$and"] = filter_doc.get("$and", []) + [
                    {
                        "$or": [
                            {"status.embedded": False},
                            {"status.embedded": {"$exists": False}},
                        ]
                    }
                ]

        page = flt.page if flt.page > 0 else 1
        page_size = flt.page_size
        if page_size <= 0 or page_size > 100:
            page_size = 20

        skip = (page - 1) * page_size

        total = self._col.count_documents(filter_doc)

        cursor = self._col.find(
            filter_doc,
            {"plain_text": 0},
            sort=[("published_at", -1), ("_id", -1)],
            skip=skip,
            limit=page_size,
        )

        items: list[Post] = []
        for doc in cursor:
            items.append(self._from_document(doc))

        return items, total

    def list_by_ids(self, ids: list[str]) -> list[Post]:
        """지정된 ObjectID 목록에 해당하는 포스트들을 반환한다."""

        if not ids:
            return []

        object_ids = [to_object_id(v) for v in ids]

        cursor = self._col.find(
            {"_id": {"$in": object_ids}},
            {"plain_text": 0},
        )

        items: list[Post] = []
        for doc in cursor:
            items.append(self._from_document(doc))

        return items

    def find_by_id(self, id_value: str) -> Post | None:
        doc = self._col.find_one(
            {"_id": to_object_id(id_value)},
            {"plain_text": 0},
        )
        if not doc:
            return None
        return self._from_document(doc)

    def get_plain_text(self, id_value: str) -> str | None:
        doc = self._col.find_one(
            {"_id": to_object_id(id_value)},
            {"plain_text": 1},
        )
        if not doc:
            return None
        value = doc.get("plain_text")
        if value is None:
            return ""
        return str(value)

    def increment_view_count(self, id_value: str) -> bool:
        result = self._col.update_one(
            {"_id": to_object_id(id_value)},
            {
                "$inc": {"view_count": 1},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )
        return result.matched_count > 0

    def update_fields(self, id_value: str, updates: dict) -> None:
        allowed_keys = {
            "plain_text",
            "thumbnail_url",
            "aisummary",
            "status",
            "embedding",
        }
        invalid_keys = [key for key in updates.keys() if key not in allowed_keys]
        if invalid_keys:
            raise ValueError(f"unsupported update fields: {invalid_keys}")

        set_doc = {"updated_at": datetime.now(timezone.utc)}
        set_doc.update(updates)
        self._col.update_one(
            {"_id": to_object_id(id_value)},
            {"$set": set_doc},
        )

    def delete_by_id(self, id_value: str) -> bool:
        result = self._col.delete_one({"_id": to_object_id(id_value)})
        return result.deleted_count > 0

    def delete_by_blog_id(self, blog_id: str) -> int:
        result = self._col.delete_many({"blog_id": to_object_id(blog_id)})
        return int(result.deleted_count)

    def list_ids_by_blog_id(self, blog_id: str) -> list[str]:
        cursor = self._col.find({"blog_id": to_object_id(blog_id)}, {"_id": 1})
        return [
            id_value
            for doc in cursor
            if (id_value := from_object_id(doc.get("_id"))) is not None
        ]

    def count_by_blog_ids(self, blog_ids: list[str]) -> dict[str, int]:
        if not blog_ids:
            return {}

        object_ids = [to_object_id(blog_id) for blog_id in blog_ids]
        pipeline = [
            {"$match": {"blog_id": {"$in": object_ids}}},
            {"$group": {"_id": "$blog_id", "count": {"$sum": 1}}},
        ]

        counts: dict[str, int] = {}
        for doc in self._col.aggregate(pipeline):
            blog_id = from_object_id(doc["_id"])
            if blog_id is not None:
                counts[blog_id] = int(doc["count"])
        return counts

    def get_tag_counts_between(
        self, published_from: datetime, published_to: datetime
    ) -> list[TagCountRow]:
        pipeline = [
            {
                "$match": {
                    "published_at": {"$gte": published_from, "$lt": published_to},
                    "status.ai_summarized": True,
                    "aisummary.tags": {"$exists": True, "$type": "array", "$ne": []},
                }
            },
            {"$unwind": "$aisummary.tags"},
            {"$match": {"aisummary.tags": {"$type": "string", "$ne": ""}}},
            {
                "$group": {
                    "_id": {"$toLower": "$aisummary.tags"},
                    "original": {"$first": "$aisummary.tags"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"count": -1, "original": 1}},
        ]

        rows: list[TagCountRow] = []
        for doc in self._col.aggregate(pipeline):
            key = str(doc["_id"]).strip()
            if not key:
                continue
            rows.append(
                {
                    "key": key,
                    "tag": str(doc.get("original") or key),
                    "count": int(doc["count"]),
                }
            )
        return rows

    def get_tag_series(
        self,
        tags: list[str],
        published_from: datetime,
        published_to: datetime,
        interval: str,
    ) -> list[TagSeriesRow]:
        if interval not in {"day", "week", "month"}:
            raise ValueError(f"unsupported trend interval: {interval}")

        tag_patterns = [
            re.compile(f"^{re.escape(tag.strip())}$", re.IGNORECASE)
            for tag in tags
            if tag.strip()
        ]
        if not tag_patterns:
            return []

        match_doc = {
            "published_at": {"$gte": published_from, "$lt": published_to},
            "status.ai_summarized": True,
            "aisummary.tags": {"$in": tag_patterns},
        }

        pipeline = [
            {"$match": match_doc},
            {"$unwind": "$aisummary.tags"},
            {"$match": {"aisummary.tags": {"$in": tag_patterns}}},
            {
                "$group": {
                    "_id": {
                        "tag": {"$toLower": "$aisummary.tags"},
                        "bucket": {
                            "$dateTrunc": {
                                "date": "$published_at",
                                "unit": interval,
                                "timezone": "UTC",
                            }
                        },
                    },
                    "original": {"$first": "$aisummary.tags"},
                    "post_count": {"$sum": 1},
                    "blog_ids": {"$addToSet": "$blog_id"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "key": "$_id.tag",
                    "tag": "$original",
                    "bucket": "$_id.bucket",
                    "post_count": 1,
                    "blog_count": {"$size": "$blog_ids"},
                }
            },
            {"$sort": {"bucket": 1, "tag": 1}},
        ]

        rows: list[TagSeriesRow] = []
        for doc in self._col.aggregate(pipeline):
            rows.append(
                {
                    "key": str(doc["key"]),
                    "tag": str(doc["tag"]),
                    "bucket": doc["bucket"],
                    "post_count": int(doc["post_count"]),
                    "blog_count": int(doc["blog_count"]),
                }
            )
        return rows

    def get_category_stats(
        self, blog_id: str | None, tags: list[str]
    ) -> dict[str, int]:
        """카테고리별 포스트 개수를 반환한다. (대소문자 무시)"""
        filter_doc: dict = {}

        if blog_id:
            filter_doc["blog_id"] = to_object_id(blog_id)

        if tags:
            tags_regex = [
                re.compile(f"^{tag.strip()}$", re.IGNORECASE)
                for tag in tags
                if tag.strip()
            ]
            if tags_regex:
                filter_doc["aisummary.tags"] = {"$in": tags_regex}

        pipeline = [
            {"$match": filter_doc},
            {"$unwind": "$aisummary.categories"},
            {
                "$group": {
                    "_id": {"$toLower": "$aisummary.categories"},
                    "original": {"$first": "$aisummary.categories"},
                    "count": {"$sum": 1},
                }
            },
        ]

        result = {}
        for doc in self._col.aggregate(pipeline):
            result[doc["original"]] = doc["count"]

        return result

    def get_tag_stats(
        self, blog_id: str | None, categories: list[str]
    ) -> dict[str, int]:
        """태그별 포스트 개수를 반환한다. (대소문자 무시)"""
        filter_doc: dict = {}

        if blog_id:
            filter_doc["blog_id"] = to_object_id(blog_id)

        if categories:
            cats_regex = [
                re.compile(f"^{cat.strip()}$", re.IGNORECASE)
                for cat in categories
                if cat.strip()
            ]
            if cats_regex:
                filter_doc["aisummary.categories"] = {"$in": cats_regex}

        pipeline = [
            {"$match": filter_doc},
            {"$unwind": "$aisummary.tags"},
            {
                "$group": {
                    "_id": {"$toLower": "$aisummary.tags"},
                    "original": {"$first": "$aisummary.tags"},
                    "count": {"$sum": 1},
                }
            },
        ]

        result = {}
        for doc in self._col.aggregate(pipeline):
            result[doc["original"]] = doc["count"]

        return result

    def get_blog_stats(
        self, categories: list[str], tags: list[str]
    ) -> list[tuple[str, str, int]]:
        """블로그별 포스트 개수를 반환한다. (blog_id, blog_name, count)"""
        filter_doc: dict = {}

        cats_regex = []
        tags_regex = []

        if categories:
            cats_regex = [
                re.compile(f"^{cat.strip()}$", re.IGNORECASE)
                for cat in categories
                if cat.strip()
            ]

        if tags:
            tags_regex = [
                re.compile(f"^{tag.strip()}$", re.IGNORECASE)
                for tag in tags
                if tag.strip()
            ]

        if cats_regex and tags_regex:
            filter_doc["$or"] = [
                {"aisummary.categories": {"$in": cats_regex}},
                {"aisummary.tags": {"$in": tags_regex}},
            ]
        elif cats_regex:
            filter_doc["aisummary.categories"] = {"$in": cats_regex}
        elif tags_regex:
            filter_doc["aisummary.tags"] = {"$in": tags_regex}

        pipeline = [
            {"$match": filter_doc},
            {
                "$group": {
                    "_id": "$blog_id",
                    "blog_name": {"$first": "$blog_name"},
                    "count": {"$sum": 1},
                }
            },
        ]

        result = []
        for doc in self._col.aggregate(pipeline):
            blog_id = from_object_id(doc["_id"])
            blog_name = doc["blog_name"]
            count = doc["count"]
            result.append((blog_id, blog_name, count))

        return result
