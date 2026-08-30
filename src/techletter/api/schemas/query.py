"""쿼리 파라미터 파싱.

FastAPI 기본 검증에 맡기면 `page=abc`가 422가 된다. 프론트는 잘못된 값이 오면
조용히 기본값을 쓰는 관용적 파싱을 기대하므로 직접 파싱한다.
빈 문자열도 "값 없음"으로 본다 — 프론트가 `categories=`를 보낸다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Query

from techletter.core.pagination import Page

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

__all__ = [
    "ListQ",
    "StrQ",
    "clean_list",
    "parse_page",
    "published_range",
]

# 목록 쿼리는 전부 문자열로 받아 우리가 해석한다. `Annotated` 형태를 쓰는 이유는
# 기본값 자리에서 `Query(...)`를 호출하지 않기 위해서다.
StrQ = Annotated[str | None, Query()]
ListQ = Annotated[list[str] | None, Query()]


def parse_page(page: str | None, page_size: str | None, *, default_size: int = 20) -> Page:
    return Page.parse(page, page_size, default_size=default_size)


def clean_list(values: list[str] | None) -> list[str]:
    """빈 문자열을 걸러내고 공백을 정리한다."""
    return [v.strip() for v in (values or []) if v and v.strip()]


def _date(raw: str | None, field: str, *, end_of_day: bool = False) -> datetime | None:
    from techletter.core.errors import InvalidRequestError  # noqa: PLC0415
    from techletter.core.time import parse_rfc3339_or_date  # noqa: PLC0415

    if raw is None or not raw.strip():
        return None
    parsed = parse_rfc3339_or_date(raw, end_of_day=end_of_day)
    if parsed is None:
        # 숫자와 달리 날짜는 조용히 무시하지 않는다. 오타 하나로 필터가
        # 통째로 사라지면 사용자는 "전체 글"을 받고도 걸러진 줄 안다.
        raise InvalidRequestError(
            "날짜 형식이 올바르지 않습니다. YYYY-MM-DD 또는 ISO-8601을 사용해 주세요.",
            details={"field": field},
        )
    return parsed


def published_range(
    published_from: str | None, published_to: str | None
) -> tuple[datetime | None, datetime | None]:
    """`published_to`가 날짜만 오면 그날 23:59:59.999까지로 본다.

    프론트가 날짜 선택기에서 `2025-03-31`을 보낸다. 그대로 쓰면 그날 00:00
    이후 글이 통째로 빠진다.
    """
    return (
        _date(published_from, "published_from"),
        _date(published_to, "published_to", end_of_day=True),
    )
