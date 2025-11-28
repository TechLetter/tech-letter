from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Mapping

from .core import Event, RetryDelays


def new_json_event(
    payload: Mapping[str, Any],
    *,
    max_retry: int | None = None,
    event_id: str | None = None,
) -> Event:
    """Go eventbus.NewJSONEvent와 동일한 JSON 래핑 동작을 수행한다.

    - id가 비어 있으면 고해상도 타임스탬프 기반 문자열을 생성한다.
    - max_retry가 1~len(RetryDelays) 범위를 벗어나면 기본값(len(RetryDelays))을 사용한다.
    """
    if max_retry is None or max_retry <= 0 or max_retry > len(RetryDelays):
        max_retry = len(RetryDelays)

    if not event_id:
        event_id = str(time.time_ns())

    # Event.dataclass가 max_retry 보정 로직을 다시 수행하므로, 여기서는 그대로 전달한다.
    return Event(id=event_id, payload=dict(payload), retry=0, max_retry=max_retry)


def event_to_dict(event: Event) -> dict[str, Any]:
    """Event를 JSON 직렬화 가능한 dict로 변환한다."""
    return asdict(event)
