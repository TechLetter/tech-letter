from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.posts import router as posts_router
from app.api.v1.blogs import router as blogs_router
from app.scheduler.rss_scheduler import start_rss_scheduler, stop_rss_scheduler
from app.event_handlers.post_events_consumer import run_post_summary_consumer
from common.logger import setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover - framework hook
    """애플리케이션 생명주기 동안 백그라운드 작업을 관리한다.

    - RSS 스케줄러 스레드
    - PostSummarized 이벤트를 소비하는 Kafka 컨슈머 스레드
    """

    start_rss_scheduler()

    summary_stop_flag = [False]
    summary_thread = threading.Thread(
        target=run_post_summary_consumer,
        args=(summary_stop_flag,),
        name="post-summary-consumer",
        daemon=True,
    )
    summary_thread.start()

    try:
        yield
    finally:
        summary_stop_flag[0] = True
        summary_thread.join(timeout=10.0)
        stop_rss_scheduler()


def create_app() -> FastAPI:
    setup_logger(name="content-service")
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


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
