from fastapi import APIRouter

from .bookmarks import router as bookmarks_router
from .chat_suggested_questions import router as suggested_questions_router
from .credits import router as credits_router
from .chat_sessions import router as sessions_router
from .users import router as users_router
from .login_sessions import router as login_sessions_router

api_router = APIRouter()
api_router.include_router(
    suggested_questions_router,
    prefix="/chatbot/suggested-questions",
    tags=["chat_suggested_questions"],
)
api_router.include_router(
    sessions_router, prefix="/chatbot/sessions", tags=["chat_sessions"]
)
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(
    credits_router
)  # prefix는 router 파일 내부에서 정의되어 있음 (/credits)
api_router.include_router(bookmarks_router, prefix="/bookmarks", tags=["bookmarks"])
api_router.include_router(
    login_sessions_router, prefix="/login-sessions", tags=["login_sessions"]
)
