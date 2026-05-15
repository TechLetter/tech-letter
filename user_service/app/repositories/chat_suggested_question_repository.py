from __future__ import annotations

from datetime import datetime
from typing import Optional

from common.mongo.types import to_object_id
from pymongo import ReturnDocument
from pymongo.database import Database

from ..models.chat_suggested_question import ChatSuggestedQuestion
from .documents.chat_suggested_question_document import (
    ChatSuggestedQuestionDocument,
)


class ChatSuggestedQuestionRepository:
    def __init__(self, db: Database):
        self.collection = db["chat_suggested_questions"]

    def list(self, include_inactive: bool = False) -> list[ChatSuggestedQuestion]:
        filter_query = {} if include_inactive else {"is_active": True}
        cursor = self.collection.find(filter_query).sort(
            [("sort_order", 1), ("created_at", 1)]
        )
        return [
            ChatSuggestedQuestionDocument.model_validate(doc).to_domain()
            for doc in cursor
        ]

    def create(
        self, question: ChatSuggestedQuestion, normalized_text: str
    ) -> ChatSuggestedQuestion:
        doc = ChatSuggestedQuestionDocument.from_domain(question, normalized_text)
        record = doc.to_mongo_record()
        result = self.collection.insert_one(record)
        doc.id = result.inserted_id
        return doc.to_domain()

    def update(
        self,
        question_id: str,
        *,
        text: str,
        normalized_text: str,
        sort_order: int,
        is_active: bool,
    ) -> Optional[ChatSuggestedQuestion]:
        updated_doc = self.collection.find_one_and_update(
            {"_id": to_object_id(question_id)},
            {
                "$set": {
                    "text": text,
                    "normalized_text": normalized_text,
                    "sort_order": sort_order,
                    "is_active": is_active,
                    "updated_at": datetime.utcnow(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated_doc:
            return None
        return ChatSuggestedQuestionDocument.model_validate(updated_doc).to_domain()

    def delete(self, question_id: str) -> bool:
        result = self.collection.delete_one({"_id": to_object_id(question_id)})
        return result.deleted_count > 0

    def find_by_normalized_text(
        self,
        normalized_text: str,
        exclude_id: str | None = None,
    ) -> Optional[ChatSuggestedQuestion]:
        filter_query = {"normalized_text": normalized_text}
        if exclude_id:
            filter_query["_id"] = {"$ne": to_object_id(exclude_id)}
        doc = self.collection.find_one(filter_query)
        if not doc:
            return None
        return ChatSuggestedQuestionDocument.model_validate(doc).to_domain()

    def next_sort_order(self) -> int:
        doc = self.collection.find_one({}, sort=[("sort_order", -1)])
        if not doc:
            return 10
        return int(doc.get("sort_order") or 0) + 10
