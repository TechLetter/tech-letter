from datetime import datetime

from pydantic import BaseModel, Field


class StatusFlags(BaseModel):
    """포스트 상태 플래그"""

    ai_summarized: bool = Field(default=False, alias="ai_summarized")


class AISummary(BaseModel):
    """AI 요약 결과"""

    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    model_name: str = Field(default="", alias="model_name")
    generated_at: datetime = Field(alias="generated_at")


class Post(BaseModel):
    """게시글 도메인 모델 (API/이벤트/저장소에서 공통 사용)"""

    id: str | None = Field(default=None, alias="id")
    created_at: datetime = Field(alias="created_at")
    updated_at: datetime = Field(alias="updated_at")
    status: StatusFlags = Field(default_factory=StatusFlags)
    view_count: int = Field(default=0, alias="view_count")
    blog_id: str = Field(alias="blog_id")
    blog_name: str = Field(alias="blog_name")
    title: str
    link: str
    published_at: datetime = Field(alias="published_at")
    thumbnail_url: str = Field(default="", alias="thumbnail_url")
    rendered_html: str = Field(default="", alias="rendered_html")
    aisummary: AISummary


class ListPostsFilter(BaseModel):
    """포스트 리스트 조회 옵션"""

    page: int = 1
    page_size: int = 20
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    blog_id: str | None = None
    blog_name: str | None = None

    # Status Filters
    # 추후 document_embedded 등 다른 status 플래그가 추가될 수 있음
    status_ai_summarized: bool | None = None
