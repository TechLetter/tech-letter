"""공통 스키마 정의."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """페이지네이션 응답 공통 스키마."""

    items: list[T]
    total: int
    page: int
    page_size: int
