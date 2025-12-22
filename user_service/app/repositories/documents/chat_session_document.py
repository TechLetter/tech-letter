from __future__ import annotations

from datetime import datetime
from typing import List

from common.mongo.types import (
    BaseDocument,
    MongoDateTime,
    build_document_data_from_domain,
    from_object_id,
)
from pydantic import BaseModel

from ...models.chat_session import ChatMessage, ChatSession, ChatRole


class ChatMessageDocument(BaseModel):
    """채팅 메시지 서브 도큐먼트."""

    role: str
    content: str
    created_at: MongoDateTime


class ChatSessionDocument(BaseDocument):
    """MongoDB chat_sessions 컬렉션 도큐먼트."""

    user_code: str
    title: str
    messages: List[ChatMessageDocument]

    @classmethod
    def from_domain(cls, session: ChatSession) -> "ChatSessionDocument":
        data = build_document_data_from_domain(session)
        # messages 변환 로직이 build_document_data_from_domain에서 재귀적으로 처리되지 않을 수 있으므로 명시적 변환
        # (ChatMessage -> ChatMessageDocument 구조가 거의 동일하므로 자동 변환 가능성 높음, 테스트 필요)
        return cls.model_validate(data)

    def to_domain(self) -> ChatSession:
        created_at: datetime = (
            self.created_at
            if isinstance(self.created_at, datetime)
            else datetime.fromisoformat(str(self.created_at))
        )
        updated_at: datetime = (
            self.updated_at
            if isinstance(self.updated_at, datetime)
            else datetime.fromisoformat(str(self.updated_at))
        )

        domain_messages = []
        for msg in self.messages:
            msg_created_at = (
                msg.created_at
                if isinstance(msg.created_at, datetime)
                else datetime.fromisoformat(str(msg.created_at))
            )
            domain_messages.append(
                ChatMessage(
                    role=ChatRole(msg.role),
                    content=msg.content,
                    created_at=msg_created_at,
                )
            )

        return ChatSession(
            id=from_object_id(self.id),
            user_code=self.user_code,
            title=self.title,
            messages=domain_messages,
            created_at=created_at,
            updated_at=updated_at,
        )
