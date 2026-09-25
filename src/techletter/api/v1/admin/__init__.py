"""어드민 API. 전부 `role=admin`을 요구한다."""

from fastapi import APIRouter

from techletter.api.v1.admin import backfill, blogs, jobs, posts, users
from techletter.api.v1.admin import suggested_questions as questions

admin_router = APIRouter(prefix="/admin")
for module in (posts, blogs, users, questions, jobs, backfill):
    admin_router.include_router(module.router)

__all__ = ["admin_router"]
