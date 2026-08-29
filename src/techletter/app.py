"""FastAPI 앱 팩토리."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from techletter import __version__
from techletter.api.errors import register_error_handlers
from techletter.api.middleware import RequestTraceMiddleware
from techletter.api.v1 import health
from techletter.api.v1.router import api_router
from techletter.core.logging import get_logger, setup_logging
from techletter.settings import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.service_name)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("api starting", extra={"version": __version__})
        # Phase 2에서 Mongo/Qdrant 클라이언트와 인덱스 보장을 붙인다.
        yield
        logger.info("api stopped")

    app = FastAPI(
        title="Tech-Letter API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # 순수 ASGI 미들웨어가 CORS보다 바깥에 오도록 마지막에 추가한다.
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.add_middleware(RequestTraceMiddleware)

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app
