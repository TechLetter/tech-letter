from fastapi import APIRouter

from .blogs import router as blogs_router
from .filters import router as filters_router
from .posts import router as posts_router

api_router = APIRouter()
api_router.include_router(posts_router, prefix="/posts", tags=["posts"])
api_router.include_router(blogs_router, prefix="/blogs", tags=["blogs"])
api_router.include_router(filters_router, prefix="/filters", tags=["filters"])
