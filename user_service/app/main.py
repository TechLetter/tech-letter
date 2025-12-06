from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.logger import setup_logger
from common.middleware.request_trace import RequestTraceMiddleware

from .api.health import router as health_router
from .api.v1 import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover - framework hook
    yield


def create_app() -> FastAPI:
    setup_logger()
    app = FastAPI(
        title="TechLetter User Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    # 공통 Request/Span ID 로그 미들웨어
    app.add_middleware(RequestTraceMiddleware)

    app.include_router(health_router, tags=["health"])
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    port = int(os.getenv("USER_SERVICE_PORT", "8002"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
