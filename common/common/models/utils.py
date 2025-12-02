from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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
