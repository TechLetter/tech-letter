"""/api/v1 라우터 조립.

**선언 순서가 중요하다.** FastAPI는 선언 순서로 매칭하므로 고정 경로를
경로 변수보다 먼저 등록해야 한다.
"""

from __future__ import annotations

from fastapi import APIRouter

from techletter.api.v1 import (
    auth,
    blogs,
    bookmarks,
    chat,
    filters,
    llm_models,
    me,
    posts,
    search,
    trends,
)
from techletter.api.v1.admin import admin_router

api_router = APIRouter(prefix="/api/v1")

for router in (
    auth.router,
    me.router,
    # /filters, /trends, /llm-models 는 /posts 보다 먼저 와도 무방하지만 읽는
    # 순서를 맞춘다.
    posts.router,
    search.router,
    bookmarks.router,
    filters.router,
    blogs.router,
    trends.router,
    llm_models.router,
    chat.router,
    admin_router,
):
    api_router.include_router(router)

__all__ = ["api_router"]
