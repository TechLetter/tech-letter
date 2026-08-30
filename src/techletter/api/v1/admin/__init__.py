"""어드민 API. 전부 `role=admin`을 요구한다."""

from fastapi import APIRouter

from techletter.api.v1.admin import backfill, blogs, jobs, llm_models, posts, users
from techletter.api.v1.admin import suggested_questions as questions

admin_router = APIRouter(prefix="/admin")
for module in (posts, blogs, users, questions, jobs, llm_models, backfill):
    admin_router.include_router(module.router)

__all__ = ["admin_router"]
