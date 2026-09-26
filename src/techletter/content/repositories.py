"""content 도메인 저장소.

인덱스 이름은 운영 DB에 이미 있는 이름과 정확히 같아야 한다 — 이름이
다르면 같은 키의 중복 인덱스가 생긴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from techletter.content.links import normalize_link
from techletter.content.models import Blog, ListPostsFilter, Post, PostSort
from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.ids import to_object_id
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from bson import ObjectId
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.core.pagination import Page

__all__ = ["BlogPostStats", "BlogRepository", "PostRepository", "TopicActivity"]


# 발행일이 생성 시각과 이만큼 가까우면 피드가 날짜를 안 준 글이다.
ESTIMATED_PUBLISHED_WINDOW_MS = 60_000


@dataclass(frozen=True, slots=True)
class BlogPostStats:
    count: int
    last_added_at: datetime | None


@dataclass(frozen=True, slots=True)
class TopicActivity:
    topic: str
    post_count: int
    blog_count: int
    recent: list[tuple[str, str]] = field(default_factory=list)
    """(post_id, blog_name), 최근 글부터."""


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
        IndexSpec("idx_posts_views", [("view_count", DESCENDING), ("published_at", DESCENDING)]),
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


def _status_conditions(flt: ListPostsFilter, query: dict[str, Any]) -> list[dict[str, Any]]:
    """요약·임베딩·실패 필터. 참 조건은 `query`에 바로 넣고, 거짓 조건은 `$and`용으로 준다."""
    conditions: list[dict[str, Any]] = []
    for field_name, value in (
        ("status.ai_summarized", flt.summarized),
        ("status.embedded", flt.embedded),
    ):
        if value is True:
            query[field_name] = True
        elif value is False:
            conditions.append(_falsy(field_name))
    if flt.failed:
        query["status.failed_reason"] = {"$nin": [None, ""]}
    return conditions


def _falsy(field: str) -> dict[str, Any]:
    """`False` 또는 필드 자체가 없는 문서를 고른다.

    오래된 포스트에는 `status.embedded`가 아예 없다. `{field: False}`만 쓰면
    그것들이 통째로 빠진다.
    """
    return {"$or": [{field: False}, {field: {"$exists": False}}]}


def _exact_ci(values: list[str]) -> list[re.Pattern[str]]:
    """대소문자를 무시하는 완전일치 패턴."""
    return [re.compile(f"^{re.escape(v.strip())}$", re.IGNORECASE) for v in values if v.strip()]


# 목록·단건 조회에서 빼는 큰 필드. 본문이 필요한 곳은 전용 메서드로 따로 읽는다.
_WITHOUT_BODIES: dict[str, int] = {"plain_text": 0, "feed_html": 0}


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

        conditions = _status_conditions(flt, query)
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
        self,
        flt: ListPostsFilter,
        page: Page,
        *,
        with_body: bool = False,
        sort: PostSort = "latest",
    ) -> tuple[list[Post], int]:
        query = self.build_query(flt)
        total = await self._col.count_documents(query)
        projection = {"feed_html": 0} if with_body else _WITHOUT_BODIES
        order = [("published_at", DESCENDING), ("_id", DESCENDING)]
        if sort == "views":
            # 조회수가 같으면(대부분 0) 최신순.
            order = [("view_count", DESCENDING), *order]
        cursor = (
            self._col.find(query, projection=projection)
            .sort(order)
            .skip(page.skip)
            .limit(page.page_size)
        )
        return [Post.model_validate(doc) async for doc in cursor], total

    async def get(self, post_id: str) -> Post | None:
        oid = to_object_id(post_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid}, projection=_WITHOUT_BODIES)
        return Post.model_validate(doc) if doc else None

    async def get_many(self, post_ids: list[str]) -> dict[str, Post]:
        """id → Post. 북마크 목록 조립용."""
        oids = [oid for oid in (to_object_id(p) for p in post_ids) if oid is not None]
        if not oids:
            return {}
        cursor = self._col.find({"_id": {"$in": oids}}, projection=_WITHOUT_BODIES)
        return {str(doc["_id"]): Post.model_validate(doc) async for doc in cursor}

    async def matching_ids(
        self, flt: ListPostsFilter, post_ids: list[str]
    ) -> dict[str, datetime | None]:
        """후보 중 필터를 통과한 글의 id → 발행일. 검색 결과를 거르고 최신성을 매길 때 쓴다."""
        oids = [oid for oid in (to_object_id(p) for p in post_ids) if oid is not None]
        if not oids:
            return {}
        query = self.build_query(flt)
        query["_id"] = {"$in": oids}
        cursor = self._col.find(query, projection={"published_at": 1})
        return {str(doc["_id"]): doc.get("published_at") async for doc in cursor}

    async def find_summarized_batch(
        self, limit: int, *, after_id: ObjectId | None = None
    ) -> list[Post]:
        """요약된 글을 `_id` 순으로 배치 조회한다(어휘 색인 백필용)."""
        query: dict[str, Any] = {"status.ai_summarized": True}
        if after_id is not None:
            query["_id"] = {"$gt": after_id}
        cursor = (
            self._col.find(query, projection=_WITHOUT_BODIES)
            .sort([("_id", ASCENDING)])
            .limit(limit)
        )
        return [Post.model_validate(doc) async for doc in cursor]

    async def get_plain_text(self, post_id: str) -> str | None:
        oid = to_object_id(post_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid}, projection={"plain_text": 1})
        return (doc or {}).get("plain_text")

    async def get_feed_html(self, post_id: str) -> str | None:
        oid = to_object_id(post_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid}, projection={"feed_html": 1})
        return (doc or {}).get("feed_html")

    async def get_plain_texts(self, post_ids: list[str]) -> dict[str, str]:
        """본문 벌크 조회. 포스트마다 개별 조회하는 N+1을 없앤다."""
        oids = [oid for oid in (to_object_id(p) for p in post_ids) if oid is not None]
        if not oids:
            return {}
        cursor = self._col.find({"_id": {"$in": oids}}, projection={"plain_text": 1})
        return {str(doc["_id"]): doc["plain_text"] async for doc in cursor if doc.get("plain_text")}

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

    async def find_by_titles(self, blog_id: Any, titles: list[str]) -> list[Post]:
        """같은 블로그에서 제목이 같은 글. 도메인을 옮긴 글을 알아보는 데 쓴다."""
        if not titles:
            return []
        cursor = self._col.find(
            {"blog_id": blog_id, "title": {"$in": titles}}, projection=_WITHOUT_BODIES
        )
        return [Post.model_validate(doc) async for doc in cursor]

    async def relink(self, post_id: str, link: str, link_key: str) -> bool:
        """글의 주소를 옮긴다. 새 주소가 이미 다른 글의 것이면 건드리지 않는다."""
        oid = to_object_id(post_id)
        if oid is None:
            return False
        try:
            result = await self._col.update_one(
                {"_id": oid},
                {"$set": {"link": link, "link_key": link_key, "updated_at": utcnow()}},
            )
        except DuplicateKeyError:
            return False
        return result.modified_count > 0

    async def save_content(self, post_id: str, plain_text: str, thumbnail_url: str) -> bool:
        """가져오기 결과를 저장한다. 요약은 이 본문으로 한다 — 재요약에 원문이 필요 없다."""
        fields: dict[str, Any] = {
            "plain_text": plain_text,
            # 원문 대신 쓸 대체 본문이었을 뿐이다. 본문을 얻었으면 자리만 차지한다.
            "feed_html": None,
            "status.failed_reason": None,
        }
        if thumbnail_url:
            fields["thumbnail_url"] = thumbnail_url
        return await self.apply_summary(post_id, fields)

    async def correct_published_at(self, post_id: str, published_at: datetime) -> bool:
        """피드에 날짜가 없어 수집 시각을 발행일로 넣어 둔 글만 페이지 날짜로 바꾼다.

        그런 글은 발행일과 생성 시각이 사실상 같다(`Aggregator._build`가 now를 넣는다).
        피드가 날짜를 준 글은 건드리지 않는다.
        """
        oid = to_object_id(post_id)
        if oid is None:
            return False
        result = await self._col.update_one(
            {
                "_id": oid,
                "$expr": {
                    "$lt": [
                        {"$abs": {"$subtract": ["$published_at", "$created_at"]}},
                        ESTIMATED_PUBLISHED_WINDOW_MS,
                    ]
                },
            },
            {"$set": {"published_at": published_at, "updated_at": utcnow()}},
        )
        return result.modified_count > 0

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

    async def stats_by_blog(self, blog_ids: list[ObjectId]) -> dict[str, BlogPostStats]:
        """블로그별 글 수와 마지막으로 새 글이 들어온 시각(`created_at` 최댓값).

        `blogs.last_fetched_at`은 RSS를 읽을 때마다 바뀐다 — 새 글이 없어도. 이쪽은 실제로
        새 글을 가져온 때다.
        """
        if not blog_ids:
            return {}
        pipeline = [
            {"$match": {"blog_id": {"$in": blog_ids}}},
            {"$group": {"_id": "$blog_id", "n": {"$sum": 1}, "last": {"$max": "$created_at"}}},
        ]
        stats = {str(b): BlogPostStats(0, None) for b in blog_ids}
        async for row in await self._col.aggregate(pipeline):
            stats[str(row["_id"])] = BlogPostStats(int(row["n"]), row.get("last"))
        return stats

    async def find_unsummarized(self, limit: int) -> list[Post]:
        """백필 대상. 오래된 것부터."""
        cursor = (
            self._col.find(
                _falsy("status.ai_summarized"),
                projection=_WITHOUT_BODIES,
            )
            .sort([("published_at", ASCENDING)])
            .limit(limit)
        )
        return [Post.model_validate(doc) async for doc in cursor]

    async def find_needing_topics(self, names: tuple[str, ...], limit: int) -> list[Post]:
        """주제 목록 밖의 카테고리를 가진 요약 글. 최근 글부터 — 트렌드가 먼저 쓴다."""
        cursor = (
            self._col.find(
                {
                    "status.ai_summarized": True,
                    "$or": [
                        {"aisummary.categories": {"$elemMatch": {"$nin": list(names)}}},
                        {"aisummary.categories": {"$size": 0}},
                    ],
                },
                projection=_WITHOUT_BODIES,
            )
            .sort([("published_at", DESCENDING)])
            .limit(limit)
        )
        return [Post.model_validate(doc) async for doc in cursor]

    async def set_categories(self, post_id: str, categories: list[str]) -> bool:
        oid = to_object_id(post_id)
        if oid is None:
            return False
        result = await self._col.update_one(
            {"_id": oid}, {"$set": {"aisummary.categories": categories, "updated_at": utcnow()}}
        )
        return result.matched_count > 0

    async def find_summarized_not_embedded(self, limit: int) -> list[Post]:
        cursor = self._col.find(
            {
                "status.ai_summarized": True,
                **_falsy("status.embedded"),
            },
            projection=_WITHOUT_BODIES,
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

    async def topic_activity(
        self, published_from: datetime, published_to: datetime
    ) -> list[TopicActivity]:
        """기간 안의 주제별 글 수·회사 수, 그리고 대표 글 후보(최근 순)."""
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "published_at": {"$gte": published_from, "$lt": published_to},
                    "status.ai_summarized": True,
                }
            },
            {
                "$project": {
                    "categories": "$aisummary.categories",
                    "blog_name": 1,
                    "published_at": 1,
                }
            },
            {"$unwind": "$categories"},
            {"$sort": {"published_at": -1}},
            {
                "$group": {
                    "_id": "$categories",
                    "post_count": {"$sum": 1},
                    "blogs": {"$addToSet": "$blog_name"},
                    "recent": {"$push": {"id": {"$toString": "$_id"}, "blog": "$blog_name"}},
                }
            },
        ]
        rows: list[TopicActivity] = []
        async for row in await self._col.aggregate(pipeline):
            if not isinstance(row["_id"], str):
                continue
            rows.append(
                TopicActivity(
                    topic=row["_id"],
                    post_count=int(row["post_count"]),
                    blog_count=len(row["blogs"]),
                    # 대표 글은 몇 개만 고른다. 후보를 다 들고 다닐 이유가 없다.
                    recent=[(r["id"], str(r.get("blog") or "")) for r in row["recent"][:30]],
                )
            )
        return rows

    async def activity_totals(
        self, published_from: datetime, published_to: datetime
    ) -> tuple[int, int]:
        """기간 안의 (요약된 글 수, 글을 낸 회사 수)."""
        query = {
            "published_at": {"$gte": published_from, "$lt": published_to},
            "status.ai_summarized": True,
        }
        posts = await self._col.count_documents(query)
        blogs = await self._col.distinct("blog_name", query)
        return posts, len(blogs)


class BlogRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["blogs"]

    async def get(self, blog_id: str) -> Blog | None:
        oid = to_object_id(blog_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid})
        return Blog.model_validate(doc) if doc else None

    async def find_conflict(
        self, *, url: str, rss_url: str, exclude_id: ObjectId | None
    ) -> str | None:
        """중복된 `rss_url`/`url`이 있으면 그 필드 이름을 준다.

        기존 데이터에 끝 슬래시가 있는 것과 없는 것이 섞여 있어 두 형태를 모두 본다.
        """
        for field_name, value in (("rss_url", rss_url), ("url", url)):
            base = value.rstrip("/")
            if not base:
                continue
            query: dict[str, Any] = {field_name: {"$in": [base, f"{base}/"]}}
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
