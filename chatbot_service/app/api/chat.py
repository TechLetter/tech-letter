from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..services.rag_service import RAGService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """채팅 요청."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000, description="사용자 질문")


class SourceInfo(BaseModel):
    """출처 정보."""

    title: str
    blog_name: str
    link: str
    score: float


class ChatResponse(BaseModel):
    """채팅 응답."""

    answer: str
    sources: list[SourceInfo]


_rag_service: RAGService | None = None


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if response_status == 429:
        return True

    try:
        from google.api_core.exceptions import ResourceExhausted  # type: ignore

        if isinstance(exc, ResourceExhausted):
            return True
    except Exception:  # noqa: BLE001
        pass

    message = str(exc).lower()
    return (
        "rate limit" in message
        or "too many requests" in message
        or "resource exhausted" in message
        or " 429" in message
        or "(429" in message
    )


def _is_temporarily_unavailable_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {502, 503, 504}:
        return True

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if response_status in {502, 503, 504}:
        return True

    message = str(exc).lower()
    return (
        "service unavailable" in message
        or "temporarily unavailable" in message
        or "gateway" in message
        or "timeout" in message
    )


def get_rag_service() -> RAGService:
    """RAG 서비스 의존성."""
    if _rag_service is None:
        raise HTTPException(
            status_code=503,
            detail="RAG service not initialized",
        )
    return _rag_service


def set_rag_service(service: RAGService) -> None:
    """RAG 서비스 설정 (앱 시작 시 호출)."""
    global _rag_service
    _rag_service = service


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    rag_service: Annotated[RAGService, Depends(get_rag_service)],
) -> ChatResponse:
    """RAG 기반 채팅 API.

    사용자 질문을 받아 Vector DB에서 관련 문서를 검색하고,
    LLM을 통해 답변을 생성합니다.
    """
    try:
        result = rag_service.chat(
            query=request.query,
        )
    except Exception as exc:
        logger.exception("chat request failed")

        if _is_rate_limit_error(exc):
            raise HTTPException(
                status_code=429,
                detail="AI API 호출이 일시적으로 제한되었습니다. 잠시 후 다시 시도해주세요.",
            ) from exc

        if _is_temporarily_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail="AI 서버가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요.",
            ) from exc

        raise HTTPException(
            status_code=500,
            detail="채팅 요청 처리 중 오류가 발생했습니다.",
        ) from exc

    sources = [
        SourceInfo(
            title=s["title"],
            blog_name=s["blog_name"],
            link=s["link"],
            score=s["score"],
        )
        for s in result.sources
    ]

    return ChatResponse(
        answer=result.answer,
        sources=sources,
    )
