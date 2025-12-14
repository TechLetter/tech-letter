from fastapi import APIRouter


from .bookmarks import router as bookmarks_router
from .login_sessions import router as login_sessions_router
from .users import router as users_router

api_router = APIRouter()
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(
    login_sessions_router,
    prefix="/login-sessions",
    tags=["login-sessions"],
)
api_router.include_router(bookmarks_router, prefix="/bookmarks", tags=["bookmarks"])
