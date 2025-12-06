from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_validators import BeforeValidator
from typing_extensions import Annotated


def ensure_utc_datetime(value: datetime) -> datetime:
    """datetime 값을 UTC 기준으로 정규화한다.

    - tzinfo 가 없으면 UTC 로 간주해 tzinfo=UTC 를 부여
    - tzinfo 가 있으면 UTC 로 변환
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_object_id(value: Any) -> ObjectId:
    """여러 타입(str, ObjectId 등)을 MongoDB ObjectId 로 변환한다."""

    if isinstance(value, ObjectId):
        return value
    if value is None:
        raise TypeError("ObjectId cannot be None")
    return ObjectId(str(value))


def from_object_id(value: Optional[ObjectId]) -> Optional[str]:
    if value is None:
        return None
    return str(value)


PyObjectId = Annotated[ObjectId, BeforeValidator(to_object_id)]
MongoDateTime = Annotated[datetime, BeforeValidator(ensure_utc_datetime)]


class BaseDocument(BaseModel):
    """MongoDB 도큐먼트용 공통 베이스 모델.

    - ObjectId 같은 임의 타입을 허용
    - alias 기반 직렬화(by_alias)를 사용할 수 있도록 한다.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    # Mongo 공통 필드
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    created_at: MongoDateTime
    updated_at: MongoDateTime

    def to_mongo_record(self) -> dict[str, Any]:
        """MongoDB 저장에 사용할 표준 레코드(dict) 직렬화.

        - by_alias=True 로 id -> _id 등의 Mongo 필드 이름과 일치시킨다.
        - exclude_none=True 로 _id=None 같은 필드를 제거해 Mongo가 ObjectId 를 생성하도록 한다.
        """

        return self.model_dump(by_alias=True, exclude_none=True)


def build_document_data_from_domain(domain_model: BaseModel) -> dict[str, Any]:
    """도메인 Pydantic 모델을 Mongo 도큐먼트 dict 로 변환하는 공통 유틸.

    - 기본은 ``domain_model.model_dump(by_alias=True)`` 결과를 그대로 사용한다.
    - created_at / updated_at 은 도메인 모델에 모두 존재한다는 전제를 따른다.
    """

    return domain_model.model_dump(by_alias=True)
