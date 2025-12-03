from __future__ import annotations

from pydantic import BaseModel, Field


class FilterItem(BaseModel):
    """필터 항목 (카테고리/태그)"""

    name: str = Field(..., description="필터 이름")
    count: int = Field(..., description="해당 필터를 가진 포스트 개수")


class CategoryFilterResponse(BaseModel):
    """카테고리 필터 응답"""

    items: list[FilterItem] = Field(default_factory=list, description="카테고리 목록")


class TagFilterResponse(BaseModel):
    """태그 필터 응답"""

    items: list[FilterItem] = Field(default_factory=list, description="태그 목록")


class BlogFilterItem(BaseModel):
    """블로그 필터 항목"""

    id: str = Field(..., description="블로그 ID")
    name: str = Field(..., description="블로그 이름")
    count: int = Field(..., description="해당 블로그의 포스트 개수")


class BlogFilterResponse(BaseModel):
    """블로그 필터 응답"""

    items: list[BlogFilterItem] = Field(default_factory=list, description="블로그 목록")
