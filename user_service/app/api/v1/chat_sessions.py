from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from common.schemas.pagination import PaginatedResponse
from app.models.chat_session import ChatSession
from app.repositories.chat_session_repository import ChatSessionRepository
from app.services.chat_session_service import ChatSessionService
from common.mongo.client import get_database as get_db

router = APIRouter()


def get_chat_session_service(db=Depends(get_db)) -> ChatSessionService:
    repo = ChatSessionRepository(db)
    return ChatSessionService(repo)


class UpdateSessionMemoryRequest(BaseModel):
    summary: str = Field(default="", max_length=12000)
    covered_message_count: int = Field(default=0, ge=0)
    status: str = Field(default="completed")
    error_message: str | None = None


@router.get("", response_model=PaginatedResponse[ChatSession])
def list_sessions(
    user_code: str = Query(..., description="유저 코드"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ChatSessionService = Depends(get_chat_session_service),
):
    return service.list_sessions(user_code, page, page_size)


@router.get("/{session_id}", response_model=ChatSession)
def get_session(
    session_id: str,
    user_code: str = Query(..., description="유저 코드"),
    service: ChatSessionService = Depends(get_chat_session_service),
):
    session = service.get_session(session_id, user_code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("", response_model=ChatSession)
def create_session(
    user_code: str = Query(..., description="유저 코드"),
    service: ChatSessionService = Depends(get_chat_session_service),
):
    """빈 세션을 생성한다. (첫 메시지 없이 채팅방 진입 시 등)"""
    return service.create_session(user_code)


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    user_code: str = Query(..., description="유저 코드"),
    service: ChatSessionService = Depends(get_chat_session_service),
):
    success = service.delete_session(session_id, user_code)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "deleted"}


@router.put("/{session_id}/memory", response_model=ChatSession)
def update_session_memory(
    session_id: str,
    body: UpdateSessionMemoryRequest,
    user_code: str = Query(..., description="유저 코드"),
    service: ChatSessionService = Depends(get_chat_session_service),
):
    session = service.update_memory(
        session_id=session_id,
        user_code=user_code,
        summary=body.summary,
        covered_message_count=body.covered_message_count,
        status=body.status,
        error_message=body.error_message,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
