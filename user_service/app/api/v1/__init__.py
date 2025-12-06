from fastapi import APIRouter

from .users import router as users_router
from .bookmarks import router as bookmarks_router
from .login_sessions import router as login_sessions_router


api_router = APIRouter()
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(bookmarks_router, tags=["bookmarks"])
api_router.include_router(
    login_sessions_router,
    prefix="/login-sessions",
    tags=["login-sessions"],
)
