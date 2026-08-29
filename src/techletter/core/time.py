"""시간 처리. 이 프로젝트의 모든 datetime은 aware UTC다."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

__all__ = ["END_OF_DAY_OFFSET", "ensure_utc", "parse_rfc3339_or_date", "to_iso_z", "utcnow"]

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# date-only 상한을 "그 날의 끝"으로 해석할 때 쓰는 오프셋.
END_OF_DAY_OFFSET = timedelta(days=1) - timedelta(microseconds=1)


def utcnow() -> datetime:
    """현재 시각(aware UTC). `datetime.utcnow()`는 naive라 금지한다."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """naive면 UTC로 간주하고, aware면 UTC로 변환한다."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_iso_z(value: datetime | None) -> str | None:
    """`2026-08-29T11:22:33.456Z` 형태로 직렬화한다(밀리초 포함).

    프론트는 전부 `new Date(str)`로 파싱하므로 오프셋이 반드시 있어야 한다.
    """
    if value is None:
        return None
    utc = ensure_utc(value)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def parse_rfc3339_or_date(raw: str, *, end_of_day: bool = False) -> datetime | None:
    """RFC3339 우선, 실패하면 `YYYY-MM-DD`로 파싱한다. 둘 다 실패하면 None.

    `end_of_day=True`이고 날짜만 주어지면 그 날의 끝(23:59:59.999999)으로 올린다.
    현행 게이트웨이의 `published_to` 동작을 유지하기 위한 것이다.
    """
    text = raw.strip()
    if not text:
        return None
    # `datetime.fromisoformat`은 3.11+에서 date-only 문자열도 받아 자정으로 준다.
    # 그러면 end_of_day 처리를 건너뛰므로 날짜만 온 경우를 먼저 가려낸다.
    if _DATE_ONLY.match(text):
        day = date.fromisoformat(text)
        start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        return start + END_OF_DAY_OFFSET if end_of_day else start
    try:
        return ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None
