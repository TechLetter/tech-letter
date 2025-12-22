from fastapi import APIRouter, Depends, HTTPException, Query

from common.schemas.pagination import PaginatedResponse
from app.models.chat_session import ChatSession
from app.repositories.chat_session_repository import ChatSessionRepository
from app.services.chat_session_service import ChatSessionService
from common.mongo.client import get_database as get_db

router = APIRouter()


def get_chat_session_service(db=Depends(get_db)) -> ChatSessionService:
    repo = ChatSessionRepository(db)
    return ChatSessionService(repo)


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
