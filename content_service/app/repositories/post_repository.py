from __future__ import annotations

from datetime import datetime
import re
from typing import Iterable

from pymongo.database import Database

from app.repositories.documents.post_document import PostDocument
from app.repositories.interfaces import PostRepositoryInterface
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

    # --- helpers -----------------------------------------------------------------
    @staticmethod
    def _to_document(post: Post) -> dict:
        doc = PostDocument.from_domain(post)

        # by_alias=True 를 사용해 id -> _id 등 Mongo 필드 이름과 일치시킨다.
        return doc.model_dump(by_alias=True)

    @staticmethod
    def _from_document(doc: dict) -> Post:
        document = PostDocument.model_validate(doc)

        return Post(
            id=from_object_id(document.id),
            created_at=document.created_at,
            updated_at=document.updated_at,
            status=document.status,
            view_count=document.view_count,
            blog_id=from_object_id(document.blog_id) or "",
            blog_name=document.blog_name,
            title=document.title,
            link=document.link,
            published_at=document.published_at,
            thumbnail_url=document.thumbnail_url,
            rendered_html=document.rendered_html,
            aisummary=document.aisummary,
        )

    # --- commands ----------------------------------------------------------------
    def is_exist_by_link(self, link: str) -> bool:
        """링크로 포스트 존재 여부를 확인한다."""

        found = self._col.find_one({"link": link}, {"_id": 1})
        return found is not None

    def insert(self, post: Post) -> str:
        """새 포스트를 삽입하고 생성된 ID 를 반환한다."""

        now = datetime.utcnow()
        if post.created_at is None:
            post.created_at = now
        post.updated_at = now

        doc = self._to_document(post)
        result = self._col.insert_one(doc)
        return str(result.inserted_id)

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

        if flt.status_ai_summarized is not None:
            filter_doc["status.ai_summarized"] = flt.status_ai_summarized

        page = flt.page if flt.page > 0 else 1
        page_size = flt.page_size
        if page_size <= 0 or page_size > 100:
            page_size = 20

        skip = (page - 1) * page_size

        total = self._col.count_documents(filter_doc)

        cursor = self._col.find(
            filter_doc,
            {"rendered_html": 0, "plain_text": 0},
            sort=[("published_at", -1), ("_id", -1)],
            skip=skip,
            limit=page_size,
        )

        items: list[Post] = []
        for doc in cursor:
            items.append(self._from_document(doc))

        return items, total

    def find_by_id(self, id_value: str) -> Post | None:
        doc = self._col.find_one(
            {"_id": to_object_id(id_value)},
            {"rendered_html": 0, "plain_text": 0},
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

    def get_rendered_html(self, id_value: str) -> str | None:
        doc = self._col.find_one(
            {"_id": to_object_id(id_value)},
            {"rendered_html": 1},
        )
        if not doc:
            return None
        value = doc.get("rendered_html")
        if value is None:
            return ""
        return str(value)

    def increment_view_count(self, id_value: str) -> bool:
        result = self._col.update_one(
            {"_id": to_object_id(id_value)},
            {"$inc": {"view_count": 1}, "$set": {"updated_at": datetime.utcnow()}},
        )
        return result.matched_count > 0

    def update_fields(self, id_value: str, updates: dict) -> None:
        set_doc = {"updated_at": datetime.utcnow()}
        set_doc.update(updates)
        self._col.update_one(
            {"_id": to_object_id(id_value)},
            {"$set": set_doc},
        )
