from datetime import datetime
from typing import List, Optional

from common.mongo.types import to_object_id
from pymongo import ReturnDocument
from pymongo.database import Database

from app.models.chat_session import ChatMessage, ChatSession
from .documents.chat_session_document import ChatMessageDocument, ChatSessionDocument


class ChatSessionRepository:
    def __init__(self, db: Database):
        self.collection = db["chat_sessions"]

    def create(self, session: ChatSession) -> ChatSession:
        doc = ChatSessionDocument.from_domain(session)
        record = doc.to_mongo_record()
        result = self.collection.insert_one(record)
        doc.id = result.inserted_id
        return doc.to_domain()

    def get_by_id(self, session_id: str, user_code: str) -> Optional[ChatSession]:
        filter_query = {"_id": to_object_id(session_id), "user_code": user_code}
        doc_data = self.collection.find_one(filter_query)
        if not doc_data:
            return None
        return ChatSessionDocument.model_validate(doc_data).to_domain()

    def list_sessions(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[List[ChatSession], int]:
        """세션 목록 조회. messages는 제외하고 메타데이터만 반환."""
        filter_query = {"user_code": user_code}
        skip = (page - 1) * page_size

        total = self.collection.count_documents(filter_query)

        # messages 필드 제외, message_count 계산을 위해 size만 조회
        cursor = (
            self.collection.find(filter_query, {"messages": 0})  # messages 제외
            .sort("updated_at", -1)
            .skip(skip)
            .limit(page_size)
        )

        items = []
        for doc in cursor:
            # messages가 없으므로 빈 리스트로 처리
            doc["messages"] = []
            items.append(ChatSessionDocument.model_validate(doc).to_domain())
        return items, total

    def add_message(
        self, session_id: str, message: ChatMessage
    ) -> Optional[ChatSession]:
        """세션에 메시지를 추가하고 updated_at을 갱신한다."""
        msg_doc = ChatMessageDocument(
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )

        updated_doc = self.collection.find_one_and_update(
            {"_id": to_object_id(session_id)},
            {
                "$push": {"messages": msg_doc.model_dump()},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=ReturnDocument.AFTER,
        )

        if not updated_doc:
            return None

        return ChatSessionDocument.model_validate(updated_doc).to_domain()

    def get_by_id_only(self, session_id: str) -> Optional[ChatSession]:
        """session_id만으로 세션을 조회한다. (내부 이벤트 핸들러용)"""
        doc_data = self.collection.find_one({"_id": to_object_id(session_id)})
        if not doc_data:
            return None
        return ChatSessionDocument.model_validate(doc_data).to_domain()

    def update_title(self, session_id: str, title: str) -> Optional[ChatSession]:
        """세션 제목을 업데이트한다."""
        updated_doc = self.collection.find_one_and_update(
            {"_id": to_object_id(session_id)},
            {"$set": {"title": title, "updated_at": datetime.utcnow()}},
            return_document=ReturnDocument.AFTER,
        )

        if not updated_doc:
            return None

        return ChatSessionDocument.model_validate(updated_doc).to_domain()

    def delete(self, session_id: str, user_code: str) -> bool:
        result = self.collection.delete_one(
            {"_id": to_object_id(session_id), "user_code": user_code}
        )
        return result.deleted_count > 0
