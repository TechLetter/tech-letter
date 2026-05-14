from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Iterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..guards.schemas import PolicyViolationError
from ..services.conversation_memory import (
    ConversationMessage,
    StoredConversationMemory,
)
from ..services.rag_service import RAGService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageInput(BaseModel):
    """대화 맥락용 메시지."""

    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=5000)
    created_at: str | None = None


class ChatMemoryInput(BaseModel):
    """저장된 대화 압축 상태."""

    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    covered_message_count: int = 0
    status: str = "none"


class ChatRequest(BaseModel):
    """채팅 요청."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000, description="사용자 질문")
    session_id: str | None = Field(default=None, description="채팅 세션 ID")
    messages: list[ChatMessageInput] = Field(
        default_factory=list,
        max_length=60,
        description="최근 세션 메시지",
    )
    memory: ChatMemoryInput | None = None


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
    agent: dict | None = None
    guard: dict | None = None
    memory: dict | None = None


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


def _build_conversation_messages(request: ChatRequest) -> list[ConversationMessage]:
    return [
        ConversationMessage(
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )
        for message in request.messages
    ]


def _build_stored_memory(request: ChatRequest) -> StoredConversationMemory | None:
    if not request.memory:
        return None
    return StoredConversationMemory(
        summary=request.memory.summary,
        covered_message_count=request.memory.covered_message_count,
        status=request.memory.status,
    )


def _to_chat_payload(result) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "sources": [
            {
                "title": source["title"],
                "blog_name": source["blog_name"],
                "link": source["link"],
                "score": source["score"],
            }
            for source in result.sources
        ],
        "agent": result.agent,
        "guard": result.guard,
        "memory": result.memory,
    }


def _format_sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _stream_chat_events(
    request: ChatRequest,
    rag_service: RAGService,
) -> Iterator[str]:
    events: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

    def publish_activity(activity: dict[str, str]) -> None:
        events.put(("activity", activity))

    def worker() -> None:
        try:
            result = rag_service.chat(
                query=request.query,
                messages=_build_conversation_messages(request),
                stored_memory=_build_stored_memory(request),
                on_activity=publish_activity,
            )
            events.put(("done", _to_chat_payload(result)))
        except PolicyViolationError as exc:
            logger.info(
                "stream chat request blocked by prompt guard: categories=%s",
                [finding.category for finding in exc.result.findings],
            )
            events.put(
                (
                    "error",
                    {
                        "code": "policy_blocked",
                        "message": exc.result.message,
                        "guard": exc.result.to_metadata(),
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("stream chat request failed")
            if _is_rate_limit_error(exc):
                code = "rate_limited"
                message = "AI API 호출이 일시적으로 제한되었습니다. 잠시 후 다시 시도해주세요."
            elif _is_temporarily_unavailable_error(exc):
                code = "chatbot_unavailable"
                message = "AI 서버가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요."
            else:
                code = "chatbot_failed"
                message = "채팅 요청 처리 중 오류가 발생했습니다."
            events.put(("error", {"code": code, "message": message}))
        finally:
            events.put(None)

    thread = threading.Thread(target=worker, daemon=True, name="chat-stream-worker")
    thread.start()

    while True:
        event = events.get()
        if event is None:
            break
        event_name, payload = event
        yield _format_sse(event_name, payload)


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
            messages=_build_conversation_messages(request),
            stored_memory=_build_stored_memory(request),
        )
    except PolicyViolationError as exc:
        logger.info(
            "chat request blocked by prompt guard: categories=%s",
            [finding.category for finding in exc.result.findings],
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "policy_blocked",
                "message": exc.result.message,
                "guard": exc.result.to_metadata(),
            },
        ) from exc
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
        agent=result.agent,
        guard=result.guard,
        memory=result.memory,
    )


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    rag_service: Annotated[RAGService, Depends(get_rag_service)],
) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat_events(request, rag_service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
