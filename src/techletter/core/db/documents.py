"""Mongo 문서 모델 공통 타입.

주의: 기존 컬렉션의 필드명은 그대로 둔다(제약 C1). DTO에서만 이름을 바꾼다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer

from techletter.core.time import ensure_utc, utcnow

__all__ = ["BaseDocument", "MongoDateTime", "PyObjectId", "oid_str"]


def _to_object_id(value: Any) -> Any:
    if isinstance(value, ObjectId) or value is None:
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return value


def _to_utc(value: Any) -> Any:
    return ensure_utc(value) if isinstance(value, datetime) else value


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(_to_object_id),
    PlainSerializer(str, return_type=str, when_used="json"),
]

# Mongo에서 읽은 datetime은 naive UTC로 올라온다. 항상 aware로 정규화한다.
MongoDateTime = Annotated[datetime, BeforeValidator(_to_utc)]


def oid_str(value: ObjectId | str | None) -> str | None:
    return str(value) if value is not None else None


class BaseDocument(BaseModel):
    """`_id`/`created_at`/`updated_at`을 공통으로 갖는 문서."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        ser_json_timedelta="float",
    )

    id: PyObjectId | None = Field(default=None, alias="_id")
    created_at: MongoDateTime = Field(default_factory=utcnow)
    updated_at: MongoDateTime = Field(default_factory=utcnow)

    def to_mongo(self, *, exclude_id: bool = True) -> dict[str, Any]:
        """삽입용 dict.

        현행 `to_mongo_record()`는 `exclude_none=True`를 써서 `_id`를 빼려다가
        **모든 None 필드를 함께 지웠다**. 그래서 "필드를 null로 지우는 갱신"이
        불가능했다(09 §3.2). 여기서는 `_id`만 명시적으로 제외한다.
        """
        data = self.model_dump(by_alias=True)
        if exclude_id or data.get("_id") is None:
            data.pop("_id", None)
        return data

    def touch(self) -> None:
        self.updated_at = utcnow()
