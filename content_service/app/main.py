from __future__ import annotations

import os

from fastapi import FastAPI

from app.api.v1.posts import router as posts_router
from app.api.v1.blogs import router as blogs_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="TechLetter Content Service",
        version="0.1.0",
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
