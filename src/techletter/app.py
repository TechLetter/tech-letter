"""FastAPI 앱 팩토리."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from techletter import __version__
from techletter.api.errors import register_error_handlers
from techletter.api.middleware import RequestTraceMiddleware
from techletter.api.schemas import ErrorBody
from techletter.api.v1 import health
from techletter.api.v1.router import api_router
from techletter.container import Container
from techletter.core.logging import get_logger, setup_logging
from techletter.settings import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.service_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("api starting", extra={"version": __version__})
        container = await Container.open(settings)
        app.state.container = container
        try:
            yield
        finally:
            await container.close()
            logger.info("api stopped")

    app = FastAPI(
        title="Tech-Letter API",
        version=__version__,
        summary="기술 블로그 큐레이션 · 요약 · RAG 챗봇",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
        # 응답 모델에 없는 필드가 새어 나가지 않게 한다.
        responses={"4XX": {"model": ErrorBody}, "5XX": {"model": ErrorBody}},
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
