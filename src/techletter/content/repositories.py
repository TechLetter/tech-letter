"""content 도메인 저장소.

인덱스 이름은 운영 DB에 이미 있는 이름과 정확히 같아야 한다 — 이름이
다르면 같은 키의 중복 인덱스가 생긴다.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from techletter.content.links import normalize_link
from techletter.content.models import Blog, ListPostsFilter, Post
from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.ids import to_object_id
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from bson import ObjectId
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.core.pagination import Page

__all__ = ["BlogRepository", "PostRepository"]

register_indexes(
    "posts",
    [
        # 기존 인덱스 — 이름을 바꾸지 않는다
        IndexSpec("idx_published_at_desc", [("published_at", DESCENDING)]),
        IndexSpec("idx_categories", [("aisummary.categories", ASCENDING)]),
        IndexSpec("idx_tags", [("aisummary.tags", ASCENDING)]),
        IndexSpec("uniq_link", [("link", ASCENDING)], unique=True),
        IndexSpec(
            "uniq_link_key",
            [("link_key", ASCENDING)],
            unique=True,
            partial_filter={"link_key": {"$type": "string"}},
        ),
        IndexSpec("idx_published_at_id_desc", [("published_at", DESCENDING), ("_id", DESCENDING)]),
        IndexSpec(
            "idx_tags_published_at",
            [("aisummary.tags", ASCENDING), ("published_at", DESCENDING)],
        ),
        IndexSpec(
            "idx_categories_published_at",
            [("aisummary.categories", ASCENDING), ("published_at", DESCENDING)],
        ),
        IndexSpec(
            "idx_posts_blog_published", [("blog_id", ASCENDING), ("published_at", DESCENDING)]
        ),
        IndexSpec("idx_posts_summarized", [("status.ai_summarized", ASCENDING)]),
    ],
)
register_indexes(
    "blogs",
    [
        IndexSpec("uniq_rss_url", [("rss_url", ASCENDING)], unique=True),
        IndexSpec("idx_blog_name", [("name", ASCENDING)]),
        IndexSpec("idx_blog_is_active", [("is_active", ASCENDING)]),
    ],
)


def _falsy(field: str) -> dict[str, Any]:
    """`False` 또는 필드 자체가 없는 문서를 고른다.

    오래된 포스트에는 `status.embedded`가 아예 없다. `{field: False}`만 쓰면
    그것들이 통째로 빠진다.
    """
    return {"$or": [{field: False}, {field: {"$exists": False}}]}


def _exact_ci(values: list[str]) -> list[re.Pattern[str]]:
    """대소문자를 무시하는 완전일치 패턴."""
    return [re.compile(f"^{re.escape(v.strip())}$", re.IGNORECASE) for v in values if v.strip()]


def _missing_link_key_query() -> dict[str, Any]:
    """정규화 키가 아직 없는 구형 문서를 고른다."""
    return {"link_key": {"$not": {"$type": "string"}}}


class PostRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["posts"]

    # ── 조회 ────────────────────────────────────────────────────────
    @staticmethod
    def build_query(flt: ListPostsFilter) -> dict[str, Any]:
        """필터를 Mongo 쿼리로 바꾼다.

        `categories`와 `tags`가 함께 오면 **OR**다.
        상태 플래그의 `False`는 "필드가 없는 경우"도 포함한다 — 오래된 문서에
        `status.embedded`가 아예 없기 때문이다.
        """
        query: dict[str, Any] = {}
        cats, tags = _exact_ci(flt.categories), _exact_ci(flt.tags)

        if cats and tags:
            query["$or"] = [
                {"aisummary.categories": {"$in": cats}},
                {"aisummary.tags": {"$in": tags}},
            ]
        elif cats:
            query["aisummary.categories"] = {"$in": cats}
        elif tags:
            query["aisummary.tags"] = {"$in": tags}

        if flt.blog_id:
            oid = to_object_id(flt.blog_id)
            # 잘못된 id면 아무것도 매치되지 않게 한다(에러 대신 빈 결과).
            query["blog_id"] = oid if oid is not None else {"$in": []}

        if flt.published_from or flt.published_to:
            published: dict[str, datetime] = {}
            if flt.published_from:
                published["$gte"] = flt.published_from
            if flt.published_to:
                published["$lte"] = flt.published_to
            query["published_at"] = published

        conditions: list[dict[str, Any]] = []
        for field_name, value in (
            ("status.ai_summarized", flt.summarized),
            ("status.embedded", flt.embedded),
        ):
            if value is True:
                query[field_name] = True
            elif value is False:
                conditions.append(_falsy(field_name))
        if flt.search:
            escaped = re.escape(flt.search.strip())
            conditions.append(
                {
                    "$or": [
                        {"title": {"$regex": escaped, "$options": "i"}},
                        {"blog_name": {"$regex": escaped, "$options": "i"}},
                    ]
                }
            )
        if conditions:
            query["$and"] = conditions
        return query

    async def list_posts(
        self, flt: ListPostsFilter, page: Page, *, with_body: bool = False
    ) -> tuple[list[Post], int]:
        query = self.build_query(flt)
        total = await self._col.count_documents(query)
        projection = None if with_body else {"plain_text": 0}
        cursor = (
            self._col.find(query, projection=projection)
            .sort([("published_at", DESCENDING), ("_id", DESCENDING)])
            .skip(page.skip)
            .limit(page.page_size)
        )
        return [Post.model_validate(doc) async for doc in cursor], total

    async def get(self, post_id: str) -> Post | None:
        oid = to_object_id(post_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid}, projection={"plain_text": 0})
        return Post.model_validate(doc) if doc else None

    async def get_many(self, post_ids: list[str]) -> dict[str, Post]:
        """id → Post. 북마크 목록 조립용."""
        oids = [oid for oid in (to_object_id(p) for p in post_ids) if oid is not None]
        if not oids:
            return {}
        cursor = self._col.find({"_id": {"$in": oids}}, projection={"plain_text": 0})
        return {str(doc["_id"]): Post.model_validate(doc) async for doc in cursor}

    async def get_plain_text(self, post_id: str) -> str | None:
        oid = to_object_id(post_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid}, projection={"plain_text": 1})
        return (doc or {}).get("plain_text")

    async def get_plain_texts(self, post_ids: list[str]) -> dict[str, str]:
        """본문 벌크 조회. 포스트마다 개별 조회하는 N+1을 없앤다."""
        oids = [oid for oid in (to_object_id(p) for p in post_ids) if oid is not None]
        if not oids:
            return {}
        cursor = self._col.find({"_id": {"$in": oids}}, projection={"plain_text": 1})
        return {str(doc["_id"]): doc["plain_text"] async for doc in cursor if doc.get("plain_text")}

    async def exists_by_link(self, link: str) -> bool:
        return await self._col.find_one({"link": link}, projection={"_id": 1}) is not None

    async def existing_links(self, links: list[str]) -> set[str]:
        """이미 저장된 링크만 골라낸다.

        항목마다 개별 조회하면 블로그 하나당 수십 번 왕복한다. 한 번에 묻는다.
        """
        if not links:
            return set()
        cursor = self._col.find({"link": {"$in": links}}, projection={"link": 1})
        return {doc["link"] async for doc in cursor}

    async def existing_link_keys(self, links: list[str], keys: list[str]) -> set[str]:
        """원문 링크와 정규화 키 양쪽 기준으로 이미 저장된 값을 찾는다.

        `link_key` 도입 전 문서와 전환 중인 문서가 함께 있으므로 두 필드를
        모두 조회한다. 매치된 문서의 두 값을 전부 반환해야 호출자가 원문과
        키 중 어느 쪽으로 들어온 중복도 놓치지 않는다.
        """
        clauses: list[dict[str, Any]] = []
        if links:
            clauses.append({"link": {"$in": links}})
        if keys:
            clauses.append({"link_key": {"$in": keys}})
        if not clauses:
            return set()
        query: dict[str, Any] = clauses[0] if len(clauses) == 1 else {"$or": clauses}
        cursor = self._col.find(query, projection={"link": 1, "link_key": 1})
        known: set[str] = set()
        async for doc in cursor:
            if isinstance(link := doc.get("link"), str):
                known.add(link)
            if isinstance(link_key := doc.get("link_key"), str):
                known.add(link_key)
        return known

    async def find_missing_link_keys(
        self, limit: int, *, after_id: ObjectId | None = None
    ) -> list[Post]:
        """정규화 키가 없는 문서를 `_id` 순으로 배치 조회한다."""
        query = _missing_link_key_query()
        if after_id is not None:
            query["_id"] = {"$gt": after_id}
        cursor = (
            self._col.find(
                query,
                projection={"_id": 1, "link": 1, "link_key": 1},
            )
            .sort([("_id", ASCENDING)])
            .limit(limit)
        )
        return [Post.model_validate(doc) async for doc in cursor]

    async def find_by_link_keys(self, keys: list[str]) -> list[Post]:
        """주어진 키를 이미 가진 문서를 조회한다(백필 충돌 확인용)."""
        if not keys:
            return []
        cursor = self._col.find(
            {"link_key": {"$in": keys}},
            projection={"_id": 1, "link": 1, "link_key": 1},
        )
        return [Post.model_validate(doc) async for doc in cursor]

    # ── 변경 ────────────────────────────────────────────────────────
    async def insert(self, post: Post) -> Post | None:
        """새 포스트를 넣는다. 두 링크 유니크 인덱스 충돌은 None을 준다.

        수집기가 링크 존재 여부를 미리 확인해도, 워커 두 개가 같은 피드를
        동시에 처리하면 그 사이에 끼어들 수 있다. 유니크 인덱스가 최종
        방어선이고, 여기서는 그 충돌을 정상 흐름으로 다룬다.
        """
        if post.link_key is None:
            post.link_key = normalize_link(post.link)
        try:
            result = await self._col.insert_one(post.to_mongo())
        except DuplicateKeyError:
            return None
        post.id = result.inserted_id
        return post

    async def increment_view(self, post_id: str) -> bool:
        oid = to_object_id(post_id)
        if oid is None:
            return False
        result = await self._col.update_one({"_id": oid}, {"$inc": {"view_count": 1}})
        return result.matched_count > 0

    async def apply_summary(self, post_id: str, fields: dict[str, Any]) -> bool:
        oid = to_object_id(post_id)
        if oid is None:
            return False
        result = await self._col.update_one(
            {"_id": oid}, {"$set": {**fields, "updated_at": utcnow()}}
        )
        return result.matched_count > 0

    async def mark_summary_failed(self, post_id: str, reason: str) -> bool:
        """영구 실패 사유를 남긴다. 어드민이 "왜 요약이 안 됐나"를 볼 수 있게."""
        return await self.apply_summary(post_id, {"status.failed_reason": reason[:300]})

    async def apply_embedding_meta(
        self, post_id: str, meta: dict[str, Any], *, embedded_at: datetime
    ) -> bool:
        """벡터 저장 결과를 문서에 반영한다.

        `status.embedded`만 점 표기로 건드려 요약 플래그를 덮지 않는다.
        """
        return await self.apply_summary(
            post_id,
            {"embedding": {**meta, "embedded_at": embedded_at}, "status.embedded": True},
        )

    async def delete(self, post_id: str) -> bool:
        oid = to_object_id(post_id)
        if oid is None:
            return False
        result = await self._col.delete_one({"_id": oid})
        return result.deleted_count > 0

    async def delete_by_blog(self, blog_id: ObjectId) -> int:
        result = await self._col.delete_many({"blog_id": blog_id})
        return result.deleted_count

    async def ids_by_blog(self, blog_id: ObjectId) -> list[str]:
        cursor = self._col.find({"blog_id": blog_id}, projection={"_id": 1})
        return [str(doc["_id"]) async for doc in cursor]

    async def count_by_blog(self, blog_ids: list[ObjectId]) -> dict[str, int]:
        if not blog_ids:
            return {}
        pipeline = [
            {"$match": {"blog_id": {"$in": blog_ids}}},
            {"$group": {"_id": "$blog_id", "n": {"$sum": 1}}},
        ]
        counts = {str(b): 0 for b in blog_ids}
        async for row in await self._col.aggregate(pipeline):
            counts[str(row["_id"])] = int(row["n"])
        return counts

    async def find_unsummarized(self, limit: int) -> list[Post]:
        """백필 대상. 오래된 것부터."""
        cursor = (
            self._col.find(
                _falsy("status.ai_summarized"),
                projection={"plain_text": 0},
            )
            .sort([("published_at", ASCENDING)])
            .limit(limit)
        )
        return [Post.model_validate(doc) async for doc in cursor]

    async def find_summarized_not_embedded(self, limit: int) -> list[Post]:
        cursor = self._col.find(
            {
                "status.ai_summarized": True,
                **_falsy("status.embedded"),
            },
            projection={"plain_text": 0},
        ).limit(limit)
        return [Post.model_validate(doc) async for doc in cursor]

    async def update_link_key(self, post_id: str, link_key: str) -> bool:
        """구형 포스트에 정규화 키를 채운다. 유니크 충돌은 건너뛴다."""
        oid = to_object_id(post_id)
        if oid is None:
            return False
        try:
            result = await self._col.update_one(
                {"_id": oid, **_missing_link_key_query()},
                {"$set": {"link_key": link_key, "updated_at": utcnow()}},
            )
        except DuplicateKeyError:
            return False
        return result.matched_count > 0

    async def find_future_published_at(
        self, now: datetime, limit: int, *, after_id: ObjectId | None = None
    ) -> list[Post]:
        """현재 시각보다 뒤인 발행일을 가진 포스트를 배치 조회한다."""
        query: dict[str, Any] = {"published_at": {"$gt": now}}
        if after_id is not None:
            query["_id"] = {"$gt": after_id}
        cursor = (
            self._col.find(
                query,
                projection={"_id": 1, "title": 1, "published_at": 1, "created_at": 1},
            )
            .sort([("_id", ASCENDING)])
            .limit(limit)
        )
        return [Post.model_validate(doc) async for doc in cursor]

    async def update_future_published_at(
        self, post_id: str, published_at: datetime, *, now: datetime
    ) -> bool:
        """아직 미래인 발행일만 백필 값으로 갱신한다."""
        oid = to_object_id(post_id)
        if oid is None:
            return False
        result = await self._col.update_one(
            {"_id": oid, "published_at": {"$gt": now}},
            {"$set": {"published_at": published_at, "updated_at": utcnow()}},
        )
        return result.matched_count > 0

    # ── 집계 ────────────────────────────────────────────────────────
    async def _facet_counts(self, unwind_field: str, match: dict[str, Any]) -> dict[str, int]:
        """배열 필드를 펼쳐 값별 개수를 센다. 대소문자를 무시해 묶고 원본 표기를 쓴다."""
        pipeline = [
            {"$match": match},
            {"$unwind": f"${unwind_field}"},
            {"$match": {unwind_field: {"$type": "string", "$ne": ""}}},
            {
                "$group": {
                    "_id": {"$toLower": f"${unwind_field}"},
                    "original": {"$first": f"${unwind_field}"},
                    "count": {"$sum": 1},
                }
            },
        ]
        result: dict[str, int] = {}
        async for row in await self._col.aggregate(pipeline):
            result[str(row["original"])] = int(row["count"])
        return result

    async def category_counts(self, blog_id: str | None, tags: list[str]) -> dict[str, int]:
        match: dict[str, Any] = {}
        if blog_id and (oid := to_object_id(blog_id)) is not None:
            match["blog_id"] = oid
        if patterns := _exact_ci(tags):
            match["aisummary.tags"] = {"$in": patterns}
        return await self._facet_counts("aisummary.categories", match)

    async def tag_counts(self, blog_id: str | None, categories: list[str]) -> dict[str, int]:
        match: dict[str, Any] = {}
        if blog_id and (oid := to_object_id(blog_id)) is not None:
            match["blog_id"] = oid
        if patterns := _exact_ci(categories):
            match["aisummary.categories"] = {"$in": patterns}
        return await self._facet_counts("aisummary.tags", match)

    async def blog_counts(
        self, categories: list[str], tags: list[str]
    ) -> list[tuple[str, str, int]]:
        match: dict[str, Any] = {}
        if patterns := _exact_ci(categories):
            match["aisummary.categories"] = {"$in": patterns}
        if patterns := _exact_ci(tags):
            match["aisummary.tags"] = {"$in": patterns}
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": "$blog_id",
                    "blog_name": {"$first": "$blog_name"},
                    "count": {"$sum": 1},
                }
            },
        ]
        rows: list[tuple[str, str, int]] = []
        async for row in await self._col.aggregate(pipeline):
            if row["_id"] is None:
                continue
            rows.append((str(row["_id"]), str(row.get("blog_name") or ""), int(row["count"])))
        return rows

    async def tag_counts_between(
        self, published_from: datetime, published_to: datetime
    ) -> list[dict[str, Any]]:
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
        rows: list[dict[str, Any]] = []
        async for row in await self._col.aggregate(pipeline):
            key = str(row["_id"]).strip()
            if key:
                rows.append(
                    {"key": key, "tag": str(row.get("original") or key), "count": int(row["count"])}
                )
        return rows

    async def tag_series(
        self,
        tags: list[str],
        published_from: datetime,
        published_to: datetime,
        interval: str,
    ) -> list[dict[str, Any]]:
        patterns = _exact_ci(tags)
        if not patterns:
            return []
        pipeline = [
            {
                "$match": {
                    "published_at": {"$gte": published_from, "$lt": published_to},
                    "status.ai_summarized": True,
                    "aisummary.tags": {"$in": patterns},
                }
            },
            {"$unwind": "$aisummary.tags"},
            {"$match": {"aisummary.tags": {"$in": patterns}}},
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
            {"$sort": {"_id.bucket": 1}},
        ]
        rows: list[dict[str, Any]] = []
        async for row in await self._col.aggregate(pipeline):
            rows.append(
                {
                    "key": str(row["_id"]["tag"]),
                    "tag": str(row.get("original") or row["_id"]["tag"]),
                    "bucket": row["_id"]["bucket"],
                    "post_count": int(row["post_count"]),
                    "blog_count": len(row.get("blog_ids") or []),
                }
            )
        return rows


class BlogRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["blogs"]

    async def get(self, blog_id: str) -> Blog | None:
        oid = to_object_id(blog_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid})
        return Blog.model_validate(doc) if doc else None

    async def get_by_rss_url(self, rss_url: str) -> Blog | None:
        doc = await self._col.find_one({"rss_url": rss_url})
        return Blog.model_validate(doc) if doc else None

    async def find_conflict(
        self, *, url: str, rss_url: str, exclude_id: ObjectId | None
    ) -> str | None:
        """중복된 `rss_url`/`url`이 있으면 그 필드 이름을 준다.

        기존 데이터에 끝 슬래시가 있는 것과 없는 것이 섞여 있어 두 형태를 모두 본다.
        """
        for field_name, value in (("rss_url", rss_url), ("url", url)):
            if not value:
                continue
            query: dict[str, Any] = {field_name: {"$in": [value, f"{value}/"]}}
            if exclude_id is not None:
                query["_id"] = {"$ne": exclude_id}
            if await self._col.find_one(query, projection={"_id": 1}):
                return field_name
        return None

    async def list_blogs(self, page: Page, *, active: bool | None = True) -> tuple[list[Blog], int]:
        """활성 여부 3상태 필터 — `True`=활성만, `False`=비활성만, `None`=전체.

        활성 쪽이 `{"$ne": False}`인 것은 `is_active` 필드가 아예 없는 구형
        문서를 활성으로 보기 위해서다. 비활성 쪽은 명시적 `False`만 본다 —
        필드 없는 문서를 비활성로 몰아넣으면 활성로 살아 있던 피드가 사라진다.
        """
        query: dict[str, Any]
        if active is None:
            query = {}
        elif active:
            query = {"is_active": {"$ne": False}}
        else:
            query = {"is_active": False}
        total = await self._col.count_documents(query)
        cursor = (
            self._col.find(query).sort([("name", ASCENDING)]).skip(page.skip).limit(page.page_size)
        )
        return [Blog.model_validate(doc) async for doc in cursor], total

    async def list_active(self) -> list[Blog]:
        """RSS 수집 대상. `is_active`가 없는 오래된 문서도 활성으로 본다."""
        cursor = self._col.find({"is_active": {"$ne": False}}).sort([("name", ASCENDING)])
        return [Blog.model_validate(doc) async for doc in cursor]

    async def insert(self, blog: Blog) -> Blog:
        result = await self._col.insert_one(blog.to_mongo())
        blog.id = result.inserted_id
        return blog

    async def update(self, blog_id: str, fields: dict[str, Any]) -> Blog | None:
        oid = to_object_id(blog_id)
        if oid is None:
            return None
        doc = await self._col.find_one_and_update(
            {"_id": oid},
            {"$set": {**fields, "updated_at": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        return Blog.model_validate(doc) if doc else None

    async def record_fetch_result(self, blog_id: ObjectId, error: str | None) -> int:
        """수집 결과를 기록한다. 에러 메시지는 200자로 자른다 — HTTP 응답
        본문을 그대로 넣으면 404 페이지 HTML이 어드민 화면에 그대로 노출된다.
        """
        now = utcnow()
        if error is None:
            await self._col.update_one(
                {"_id": blog_id},
                {
                    "$set": {"last_fetched_at": now, "last_fetch_error": None, "updated_at": now},
                    "$unset": {"consecutive_failures": ""},
                },
            )
            return 0
        doc = await self._col.find_one_and_update(
            {"_id": blog_id},
            {
                "$set": {
                    "last_fetched_at": now,
                    "last_fetch_error": error[:200],
                    "updated_at": now,
                },
                "$inc": {"consecutive_failures": 1},
            },
            return_document=ReturnDocument.AFTER,
            projection={"consecutive_failures": 1},
        )
        return int((doc or {}).get("consecutive_failures") or 0)

    async def deactivate(self, blog_id: ObjectId, reason: str) -> None:
        await self._col.update_one(
            {"_id": blog_id},
            {
                "$set": {
                    "is_active": False,
                    "last_fetch_error": reason[:200],
                    "updated_at": utcnow(),
                }
            },
        )

    async def delete(self, blog_id: str) -> bool:
        oid = to_object_id(blog_id)
        if oid is None:
            return False
        result = await self._col.delete_one({"_id": oid})
        return result.deleted_count > 0
