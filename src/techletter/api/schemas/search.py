"""검색 결과 AI 요약."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

from techletter.core.ids import is_object_id

if TYPE_CHECKING:  # pragma: no cover
    from techletter.search.summary import SearchSummary

__all__ = ["SearchSummaryContinueIn", "SearchSummaryIn", "SearchSummaryOut"]

MAX_SELECTED_POSTS = 8


class SearchSummaryIn(BaseModel):
    query: str = Field(min_length=2, max_length=100)
    post_ids: list[str] = Field(min_length=1, max_length=MAX_SELECTED_POSTS)
    """검색 결과 순서 그대로. 이 글들만 근거로 답한다."""

    @field_validator("post_ids")
    @classmethod
    def _post_ids(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(v.strip() for v in value if v.strip()))
        if not cleaned or any(not is_object_id(v) for v in cleaned):
            raise ValueError("post_ids must be post ids")
        return cleaned


class SearchSummaryOut(BaseModel):
    key: str
    answer: str
    sources: list[dict[str, Any]]
    model_id: str | None
    cached: bool

    @classmethod
    def of(cls, summary: SearchSummary) -> SearchSummaryOut:
        return cls(
            key=summary.key,
            answer=summary.answer,
            sources=summary.sources,
            model_id=summary.model_id,
            cached=summary.cached,
        )


class SearchSummaryContinueIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
