"""공통 응답 봉투 (04 §1.2).

현행은 목록 봉투가 7종이었다. 여기서는 하나다. 페이지네이션이 의미 없는
목록(필터 등)은 `page`·`page_size`·`total_pages`를 생략한다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from techletter.core.pagination import Page

__all__ = ["ErrorBody", "ErrorDetail", "JobAccepted", "Listing", "Paged"]


class Listing[T](BaseModel):
    """페이지 개념이 없는 목록. 필터·추천 질문처럼 전량을 주는 응답."""

    items: list[T]
    total: int

    @classmethod
    def of(cls, items: list[T]) -> Listing[T]:
        return cls(items=items, total=len(items))


class Paged[T](Listing[T]):
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def of_page(cls, items: list[T], total: int, page: Page) -> Paged[T]:
        return cls(
            items=items,
            total=total,
            page=page.page,
            page_size=page.page_size,
            total_pages=page.total_pages(total),
        )


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorBody(BaseModel):
    """04 §1.3. 문서화용 — 실제 응답은 `AppError.to_body()`가 만든다."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"error": {"code": "credit.insufficient", "message": "크레딧이 부족합니다."}}
        }
    )

    error: ErrorDetail


class JobAccepted(BaseModel):
    """202 응답 (04 §1.5)."""

    job_id: str | None
