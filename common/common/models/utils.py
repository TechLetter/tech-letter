from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Annotated

from pydantic.functional_serializers import PlainSerializer


def normalize_id_fields_to_str(data: Any, *, fields: list[str]) -> Any:
    if not isinstance(data, Mapping):
        return data

    changed = False
    result: dict[str, Any] = dict(data)
    for field in fields:
        value = result.get(field)
        if value is None or isinstance(value, str):
            continue
        result[field] = str(value)
        changed = True

    if not changed:
        return data

    return result


def serialize_datetime_to_utc_iso8601(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


UtcDateTime = Annotated[
    datetime,
    PlainSerializer(
        serialize_datetime_to_utc_iso8601,
        return_type=str,
        when_used="json",
    ),
]
