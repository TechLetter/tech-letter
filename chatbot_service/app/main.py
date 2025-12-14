from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from common.logger import setup_logger
from common.middleware.request_trace import RequestTraceMiddleware

from .api.chat import router as chat_router, set_rag_service
from .config import load_config
from .event_handlers.embed_consumer import run_embed_consumer
from .services.rag_service import RAGService
from .vector_store import VectorStore


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """앱 생명주기 관리.

    - 시작 시: Vector Store, RAG Service 초기화, Embed Consumer 스레드 시작
    - 종료 시: Consumer 스레드 정리
    """
    logger.info("chatbot-service (python) starting up")

    # 설정 로드
    config = load_config()

    # Vector Store 초기화
    vector_store = VectorStore(config.qdrant)
    logger.info("vector store initialized")

    # RAG Service 초기화 및 설정
    rag_service = RAGService(
        llm_config=config.llm,
        embedding_config=config.embedding,
        vector_store=vector_store,
        default_top_k=config.rag.top_k,
        default_score_threshold=config.rag.score_threshold,
    )
    set_rag_service(rag_service)
    logger.info("rag service initialized")

    # Embed Consumer 스레드 시작
    stop_flag = [False]
    consumer_thread = threading.Thread(
        target=run_embed_consumer,
        args=(stop_flag, vector_store),
        daemon=True,
        name="embed-consumer",
    )
    consumer_thread.start()
    logger.info("embed consumer thread started")

    yield

    # 종료 처리
    logger.info("chatbot-service shutting down")
    stop_flag[0] = True
    consumer_thread.join(timeout=5.0)
    logger.info("chatbot-service stopped")


def create_app() -> FastAPI:
    """FastAPI 앱 팩토리."""
    setup_logger()
    app = FastAPI(
        title="Tech-Letter Chatbot Service",
        description="RAG 기반 기술 블로그 챗봇 서비스",
        version="0.1.0",
        lifespan=lifespan,
    )

    # 공통 Request/Span ID 로그 미들웨어
    app.add_middleware(RequestTraceMiddleware)

    # 라우터 등록
    app.include_router(chat_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "chatbot-service"}

    return app


app = create_app()


def main() -> None:
    """Chatbot Service 메인 엔트리 포인트."""
    import uvicorn

    port = int(os.getenv("CHATBOT_SERVICE_PORT", "8003"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
