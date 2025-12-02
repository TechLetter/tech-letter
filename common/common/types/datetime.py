from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic.functional_serializers import PlainSerializer


def serialize_datetime_to_utc_iso8601(value: datetime) -> str:
    """모든 datetime을 UTC 기준 ISO8601(+타임존) 문자열로 직렬화한다."""
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
