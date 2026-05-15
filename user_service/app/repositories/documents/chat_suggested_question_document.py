from __future__ import annotations

from datetime import datetime

from common.mongo.types import (
    BaseDocument,
    MongoDateTime,
    build_document_data_from_domain,
    from_object_id,
)

from ...models.chat_suggested_question import ChatSuggestedQuestion


class ChatSuggestedQuestionDocument(BaseDocument):
    """MongoDB chat_suggested_questions 컬렉션 도큐먼트."""

    text: str
    normalized_text: str
    sort_order: int = 0
    is_active: bool = True
    created_at: MongoDateTime
    updated_at: MongoDateTime

    @classmethod
    def from_domain(
        cls, question: ChatSuggestedQuestion, normalized_text: str
    ) -> "ChatSuggestedQuestionDocument":
        data = build_document_data_from_domain(question)
        data["normalized_text"] = normalized_text
        return cls.model_validate(data)

    def to_domain(self) -> ChatSuggestedQuestion:
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
        return ChatSuggestedQuestion(
            id=from_object_id(self.id),
            text=self.text,
            sort_order=self.sort_order,
            is_active=self.is_active,
            created_at=created_at,
            updated_at=updated_at,
        )
