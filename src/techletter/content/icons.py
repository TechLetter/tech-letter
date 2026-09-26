"""블로그 아이콘 저장소.

64px webp 한 장을 `blog_icons` 문서에 바이트로 둔다(개당 수 KB, 블로그 수십 개).
수집은 요약 워커가 한다(`summary/icons.py` — 이미지 변환 라이브러리가 그 이미지에만
있다). 어드민이 직접 올린 아이콘(`manual`)은 자동 수집이 덮지 않는다.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from bson import Binary

from techletter.core.ids import to_object_id
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.core.jobs.models import Job
    from techletter.core.jobs.queue import JobQueue

__all__ = [
    "COLLECTION",
    "ICON_MAX_BYTES",
    "BlogIconRepository",
    "enqueue_icon_fetch",
    "is_webp",
]

COLLECTION = "blog_icons"
# 64px webp는 보통 2~5KB다. 이보다 크면 변환이 잘못된 것이다.
ICON_MAX_BYTES = 100 * 1024


def is_webp(data: bytes) -> bool:
    return len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


class BlogIconRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db[COLLECTION]

    async def get(self, blog_id: str) -> dict[str, Any] | None:
        """아이콘이 있으면 {data, hash}. 없거나 수집에 실패했으면 None."""
        oid = to_object_id(blog_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid, "data": {"$ne": None}})
        if doc is None:
            return None
        return {"data": bytes(doc["data"]), "hash": doc["hash"]}

    async def is_manual(self, blog_id: str) -> bool:
        oid = to_object_id(blog_id)
        return bool(oid and await self._col.find_one({"_id": oid, "manual": True}, {"_id": 1}))

    async def save(self, blog_id: str, data: bytes, *, source: str, manual: bool) -> str:
        oid = to_object_id(blog_id)
        if oid is None:
            msg = f"invalid blog id: {blog_id}"
            raise ValueError(msg)
        digest = hashlib.sha1(data).hexdigest()[:12]  # 캐시 키일 뿐이다
        await self._col.update_one(
            {"_id": oid},
            {
                "$set": {
                    "data": Binary(data),
                    "hash": digest,
                    "source": source,
                    "manual": manual,
                    "updated_at": utcnow(),
                }
            },
            upsert=True,
        )
        return digest

    async def mark_missing(self, blog_id: str) -> None:
        """자동 수집이 아무것도 못 찾았다. 화면은 이름 첫 글자로 대신한다."""
        oid = to_object_id(blog_id)
        if oid is not None:
            # 어드민이 올린 아이콘은 핸들러가 먼저 건너뛴다(`is_manual`).
            await self._col.update_one(
                {"_id": oid},
                {"$set": {"data": None, "hash": None, "manual": False, "updated_at": utcnow()}},
                upsert=True,
            )

    async def release_manual(self, blog_id: str) -> None:
        """자동 수집이 다시 덮을 수 있게 한다(어드민의 "다시 받기")."""
        oid = to_object_id(blog_id)
        if oid is not None:
            await self._col.update_one({"_id": oid}, {"$set": {"manual": False}})

    async def blog_ids_with_record(self) -> set[str]:
        return {str(doc["_id"]) async for doc in self._col.find({}, {"_id": 1})}


async def enqueue_icon_fetch(queue: JobQueue, blog_id: str) -> Job | None:
    from techletter.core.jobs.types import JobType  # noqa: PLC0415

    return await queue.enqueue(JobType.BLOG_ICON_REQUESTED, blog_id, {"blog_id": blog_id})
