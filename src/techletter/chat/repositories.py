"""chat 도메인 저장소."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from techletter.chat.models import ChatMessage, ChatSession, SessionMemory, SuggestedQuestion
from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.errors import ResourceConflictError
from techletter.core.ids import to_object_id
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.core.pagination import Page

__all__ = [
    "ChatSessionRepository",
    "SessionSummary",
    "SuggestedQuestionRepository",
    "normalize_question",
]


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """목록 항목. 메시지 본문 없이 개수만 들고 있다."""

    session: ChatSession
    message_count: int


register_indexes(
    "chat_sessions",
    [IndexSpec("idx_chat_user_updated", [("user_code", ASCENDING), ("updated_at", DESCENDING)])],
)
register_indexes(
    "chat_suggested_questions",
    [IndexSpec("uniq_suggested_normalized", [("normalized_text", ASCENDING)], unique=True)],
)

_WHITESPACE = re.compile(r"\s+")


def normalize_question(text: str) -> str:
    """중복 검사용 키. 공백을 접고 대소문자를 없앤다(casefold)."""
    return _WHITESPACE.sub(" ", text).strip().casefold()


class ChatSessionRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["chat_sessions"]

    async def create(self, session: ChatSession) -> ChatSession:
        result = await self._col.insert_one(session.to_mongo())
        session.id = result.inserted_id
        return session

    async def get(self, session_id: str, user_code: str | None = None) -> ChatSession | None:
        """`user_code`를 주면 소유자까지 확인한다.

        내부 잡 핸들러는 소유자를 모르고 세션 id만 들고 오므로 생략할 수 있다.
        API 경로에서는 **반드시** 넘겨야 한다.
        """
        oid = to_object_id(session_id)
        if oid is None:
            return None
        query: dict[str, Any] = {"_id": oid}
        if user_code is not None:
            query["user_code"] = user_code
        doc = await self._col.find_one(query)
        return ChatSession.model_validate(doc) if doc else None

    async def list_sessions(self, user_code: str, page: Page) -> tuple[list[SessionSummary], int]:
        """목록에서는 본문을 빼고 개수만 센다.

        세션 하나에 메시지가 수십 개고 각 메시지에 답변 전문이 들어 있다.
        현행은 `{"messages": 0}`으로 빼고 빈 배열을 채워 넣어 프론트가 개수를
        알 방법이 없었다(04 §3.5). `$size`로 서버에서 센다.
        """
        query = {"user_code": user_code}
        total = await self._col.count_documents(query)
        cursor = await self._col.aggregate(
            [
                {"$match": query},
                {"$sort": {"updated_at": -1}},
                {"$skip": page.skip},
                {"$limit": page.page_size},
                {"$addFields": {"message_count": {"$size": {"$ifNull": ["$messages", []]}}}},
                {"$project": {"messages": 0}},
            ]
        )
        return [
            SessionSummary(
                session=ChatSession.model_validate(doc),
                message_count=int(doc.get("message_count") or 0),
            )
            async for doc in cursor
        ], total

    async def message_counts(self, session_ids: list[str]) -> dict[str, int]:
        oids = [oid for oid in (to_object_id(s) for s in session_ids) if oid is not None]
        if not oids:
            return {}
        pipeline = [
            {"$match": {"_id": {"$in": oids}}},
            {"$project": {"n": {"$size": {"$ifNull": ["$messages", []]}}}},
        ]
        return {str(row["_id"]): int(row["n"]) async for row in await self._col.aggregate(pipeline)}

    async def append_message(self, session_id: str, message: ChatMessage) -> ChatSession | None:
        oid = to_object_id(session_id)
        if oid is None:
            return None
        doc = await self._col.find_one_and_update(
            {"_id": oid},
            {"$push": {"messages": message.to_mongo()}, "$set": {"updated_at": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        return ChatSession.model_validate(doc) if doc else None

    async def set_title(self, session_id: str, title: str) -> bool:
        oid = to_object_id(session_id)
        if oid is None:
            return False
        result = await self._col.update_one(
            {"_id": oid}, {"$set": {"title": title, "updated_at": utcnow()}}
        )
        return result.matched_count > 0

    async def set_memory(self, session_id: str, memory: SessionMemory) -> ChatSession | None:
        """압축 메모리를 갱신한다. `updated_at`은 건드리지 않는다.

        압축은 백그라운드 잡이다. 여기서 `updated_at`을 올리면 세션 목록의
        정렬이 사용자가 만지지도 않은 세션 때문에 뒤바뀐다(현행 버그).
        """
        oid = to_object_id(session_id)
        if oid is None:
            return None
        doc = await self._col.find_one_and_update(
            {"_id": oid},
            {"$set": {"memory": memory.to_mongo()}},
            return_document=ReturnDocument.AFTER,
        )
        return ChatSession.model_validate(doc) if doc else None

    async def claim_compression(self, session_id: str) -> bool:
        """압축을 `pending`으로 선점한다. 이미 pending이면 False다.

        원자적으로 하지 않으면 연달아 오는 메시지가 같은 압축 잡을 두 번 만든다.
        갱신 파이프라인을 쓰는 이유는 **기존 요약을 보존**하면서 상태만 바꾸기
        위해서다 — 압축이 끝나기 전까지는 직전 요약으로 답해야 한다.
        """
        oid = to_object_id(session_id)
        if oid is None:
            return False
        result = await self._col.update_one(
            {"_id": oid, "memory.status": {"$ne": "pending"}},
            [
                {
                    "$set": {
                        "memory": {
                            "summary": {"$ifNull": ["$memory.summary", ""]},
                            "covered_message_count": {
                                "$ifNull": ["$memory.covered_message_count", 0]
                            },
                            "status": "pending",
                            "requested_at": "$$NOW",
                            "updated_at": {"$ifNull": ["$memory.updated_at", None]},
                            "error_message": None,
                        }
                    }
                }
            ],
        )
        return result.modified_count > 0

    async def delete(self, session_id: str, user_code: str) -> bool:
        oid = to_object_id(session_id)
        if oid is None:
            return False
        result = await self._col.delete_one({"_id": oid, "user_code": user_code})
        return result.deleted_count > 0

    async def delete_by_user(self, user_code: str) -> int:
        result = await self._col.delete_many({"user_code": user_code})
        return result.deleted_count


class SuggestedQuestionRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["chat_suggested_questions"]

    async def list_questions(self, *, include_inactive: bool = False) -> list[SuggestedQuestion]:
        query: dict[str, Any] = {} if include_inactive else {"is_active": True}
        cursor = self._col.find(query).sort([("sort_order", ASCENDING), ("created_at", ASCENDING)])
        return [SuggestedQuestion.model_validate(doc) async for doc in cursor]

    async def get(self, question_id: str) -> SuggestedQuestion | None:
        oid = to_object_id(question_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid})
        return SuggestedQuestion.model_validate(doc) if doc else None

    async def create(self, question: SuggestedQuestion) -> SuggestedQuestion:
        try:
            result = await self._col.insert_one(question.to_mongo())
        except DuplicateKeyError as exc:
            raise ResourceConflictError("duplicate suggested question", field="text") from exc
        question.id = result.inserted_id
        return question

    async def update(self, question_id: str, fields: dict[str, Any]) -> SuggestedQuestion | None:
        oid = to_object_id(question_id)
        if oid is None:
            return None
        try:
            doc = await self._col.find_one_and_update(
                {"_id": oid},
                {"$set": {**fields, "updated_at": utcnow()}},
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise ResourceConflictError("duplicate suggested question", field="text") from exc
        return SuggestedQuestion.model_validate(doc) if doc else None

    async def delete(self, question_id: str) -> bool:
        oid = to_object_id(question_id)
        if oid is None:
            return False
        result = await self._col.delete_one({"_id": oid})
        return result.deleted_count > 0

    async def next_sort_order(self) -> int:
        """맨 뒤에 붙일 순번. 10씩 띄워 사이에 끼워 넣을 여지를 남긴다."""
        doc = await self._col.find_one({}, sort=[("sort_order", DESCENDING)])
        return int((doc or {}).get("sort_order") or 0) + 10
