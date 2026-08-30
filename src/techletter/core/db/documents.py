"""Mongo 문서 모델 공통 타입."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer

from techletter.core.time import ensure_utc, utcnow

__all__ = ["BaseDocument", "MongoDateTime", "PyObjectId", "SubDocument", "oid_str"]


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


_CONFIG = ConfigDict(
    arbitrary_types_allowed=True,
    populate_by_name=True,
    ser_json_timedelta="float",
)


class SubDocument(BaseModel):
    """다른 문서 **안에** 들어가는 값.

    `_id`도 타임스탬프도 없다. `BaseDocument`를 중첩에 쓰면 `to_mongo()`가
    하위 객체까지 재귀 덤프하면서 `_id: null`과 자체 `created_at`을 심는다 —
    `posts.status`에 쓸모없는 `_id`가 박히는 식이다.
    """

    model_config = _CONFIG

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class BaseDocument(BaseModel):
    """`_id`/`created_at`/`updated_at`을 공통으로 갖는 최상위 문서."""

    model_config = _CONFIG

    id: PyObjectId | None = Field(default=None, alias="_id")
    created_at: MongoDateTime = Field(default_factory=utcnow)
    updated_at: MongoDateTime = Field(default_factory=utcnow)

    def to_mongo(self, *, exclude_id: bool = True) -> dict[str, Any]:
        """삽입용 dict.

        `exclude_none=True`는 쓰지 않는다 — `_id`뿐 아니라 값이 `None`인 다른
        필드까지 함께 지워져서, "필드를 null로 지우는 갱신"이 불가능해진다.
        `_id`만 명시적으로 제외한다.
        """
        data = self.model_dump(by_alias=True)
        if exclude_id or data.get("_id") is None:
            data.pop("_id", None)
        return data

    def touch(self) -> None:
        self.updated_at = utcnow()
