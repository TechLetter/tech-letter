"""페이지네이션과 관용적 쿼리 파싱.

`page=abc`처럼 파싱할 수 없는 값은 422로 거절하지 않고 조용히 기본값으로
넘어간다 — 프론트가 그 동작에 기대고 있다. FastAPI 기본 검증에 맡기면
422가 되므로 여기서 직접 파싱한다.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DEFAULT_PAGE_SIZE", "MAX_PAGE_SIZE", "Page", "lenient_bool", "lenient_int"]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def lenient_int(
    raw: str | int | None,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """파싱 실패·빈 값이면 기본값을 쓰고, 범위를 벗어나면 잘라낸다.

    >>> lenient_int("abc", default=1)
    1
    >>> lenient_int("0", default=20, minimum=1)
    1
    """
    value: int
    if isinstance(raw, int):
        value = raw
    elif raw is None or not str(raw).strip():
        value = default
    else:
        try:
            value = int(str(raw).strip())
        except ValueError:
            value = default
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def lenient_bool(raw: str | bool | None) -> bool | None:
    """`true/false/1/0/yes/no`만 인식하고 그 외에는 None(필터 미적용)을 준다."""
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "no", "n", "f"}:
        return False
    return None


@dataclass(frozen=True, slots=True)
class Page:
    """1-base 페이지 파라미터."""

    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @classmethod
    def parse(
        cls,
        page: str | int | None = None,
        page_size: str | int | None = None,
        *,
        default_size: int = DEFAULT_PAGE_SIZE,
        max_size: int = MAX_PAGE_SIZE,
    ) -> Page:
        return cls(
            page=lenient_int(page, default=1, minimum=1),
            page_size=lenient_int(page_size, default=default_size, minimum=1, maximum=max_size),
        )

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size

    def total_pages(self, total: int) -> int:
        if total <= 0:
            return 0
        return -(-total // self.page_size)  # ceil
