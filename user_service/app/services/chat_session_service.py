from datetime import datetime
from typing import Optional

from common.schemas.pagination import PaginatedResponse
from ..models.chat_session import ChatSession, ChatMessage, ChatRole
from ..repositories.chat_session_repository import ChatSessionRepository


class ChatSessionService:
    def __init__(self, repo: ChatSessionRepository):
        self.repo = repo

    def create_session(
        self, user_code: str, first_message: Optional[str] = None
    ) -> ChatSession:
        """새로운 대화 세션을 생성한다. 첫 메시지가 있으면 제목을 자동 생성한다."""
        title = "New Chat"
        messages = []

        if first_message:
            # 제목은 첫 30자 + ...
            title = (
                first_message[:30] + "..." if len(first_message) > 30 else first_message
            )
            messages.append(ChatMessage(role=ChatRole.USER, content=first_message))

        session = ChatSession(
            user_code=user_code,
            title=title,
            messages=messages,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        return self.repo.create(session)

    def get_session(self, session_id: str, user_code: str) -> Optional[ChatSession]:
        return self.repo.get_by_id(session_id, user_code)

    def list_sessions(
        self, user_code: str, page: int, page_size: int
    ) -> PaginatedResponse[ChatSession]:
        items, total = self.repo.list_sessions(user_code, page, page_size)
        return PaginatedResponse(
            total=total, page=page, page_size=page_size, items=items
        )

    def delete_session(self, session_id: str, user_code: str) -> bool:
        return self.repo.delete(session_id, user_code)

    def add_message(
        self, session_id: str, role: ChatRole, content: str
    ) -> Optional[ChatSession]:
        """세션에 메시지를 추가한다.

        첫 user 메시지이고 title이 'New Chat'인 경우 제목을 자동 생성한다.
        """
        # 현재 세션 조회
        # Note: session_id만으로 조회 (user_code 검증은 이벤트 핸들러에서 신뢰)
        current = self.repo.get_by_id_only(session_id)

        if not current:
            return None

        # 첫 user 메시지이고 title이 "New Chat"인 경우 제목 자동 생성
        if (
            role == ChatRole.USER
            and current.title == "New Chat"
            and len(current.messages) == 0
        ):
            new_title = content[:30] + "..." if len(content) > 30 else content
            self.repo.update_title(session_id, new_title)

        message = ChatMessage(role=role, content=content)
        return self.repo.add_message(session_id, message)
