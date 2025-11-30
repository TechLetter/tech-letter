from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.posts import router as posts_router
from app.api.v1.blogs import router as blogs_router
from app.scheduler.rss_scheduler import start_rss_scheduler, stop_rss_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover - framework hook
    """애플리케이션 생명주기 동안 RSS 스케줄러를 관리한다."""

    start_rss_scheduler()
    try:
        yield
    finally:
        stop_rss_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="TechLetter Content Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(posts_router, prefix="/api/v1/posts", tags=["posts"])
    app.include_router(blogs_router, prefix="/api/v1/blogs", tags=["blogs"])

    return app


app = create_app()


def main() -> None:
    """명령행에서 실행할 수 있도록 uvicorn 런처를 제공한다."""

    import uvicorn

    port = int(os.getenv("CONTENT_SERVICE_PORT", "8001"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
