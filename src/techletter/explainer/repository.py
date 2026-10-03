"""`post_explainers` — 글마다 하나."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pymongo import ASCENDING

from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.ids import to_object_id
from techletter.core.time import utcnow
from techletter.explainer.models import Explainer

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

__all__ = ["COLLECTION", "ExplainerRepository"]

COLLECTION = "post_explainers"

register_indexes(COLLECTION, [IndexSpec("uniq_post_id", [("post_id", ASCENDING)], unique=True)])


class ExplainerRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db[COLLECTION]

    async def upsert(self, explainer: Explainer) -> None:
        doc = explainer.to_mongo()
        doc["updated_at"] = utcnow()
        created = doc.pop("created_at", utcnow())
        await self._col.update_one(
            {"post_id": explainer.post_id},
            {"$set": doc, "$setOnInsert": {"created_at": created}},
            upsert=True,
        )

    async def get(self, post_id: str) -> Explainer | None:
        oid = to_object_id(post_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"post_id": oid})
        return Explainer.model_validate(doc) if doc else None

    async def delete(self, post_ids: list[str]) -> int:
        oids = [oid for oid in (to_object_id(p) for p in post_ids) if oid is not None]
        if not oids:
            return 0
        return (await self._col.delete_many({"post_id": {"$in": oids}})).deleted_count
