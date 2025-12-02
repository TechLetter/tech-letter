from __future__ import annotations

from typing import Annotated, Any

from pydantic.functional_validators import BeforeValidator


def _to_object_id_str(value: Any) -> Any:
    """Mongo ObjectId 등 다양한 타입을 안전하게 문자열 ID로 변환한다.

    - None 이나 이미 문자열이면 그대로 반환
    - 그 외 타입(ObjectId 등)은 str() 로 변환
    """

    if value is None or isinstance(value, str):
        return value
    return str(value)


ObjectIdStr = Annotated[str, BeforeValidator(_to_object_id_str)]
