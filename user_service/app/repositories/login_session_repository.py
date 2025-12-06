from __future__ import annotations

from datetime import datetime, timezone

from pymongo.database import Database

from common import logger

from ..models.login_session import LoginSession
from .documents.login_session_document import LoginSessionDocument


class LoginSessionRepository:
    """login_sessions 컬렉션에 대한 MongoDB 접근 레이어."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._col = database["login_sessions"]

    def create(self, session: LoginSession) -> LoginSession:
        document = LoginSessionDocument.from_domain(session)
        payload = document.to_mongo_record()
        self._col.insert_one(payload)
        return session

    def delete_by_session_id(self, session_id: str) -> LoginSession | None:
        # 세션은 한 번만 사용 가능해야 하므로 find_one_and_delete 를 사용해 즉시 삭제한다.
        raw = self._col.find_one_and_delete({"session_id": session_id})
        if not raw:
            return None

        document = LoginSessionDocument.model_validate(raw)
        session = document.to_domain()

        # TTL 인덱스는 지연될 수 있으므로 애플리케이션 레벨에서도 만료를 한 번 더 확인한다.
        now = datetime.now(timezone.utc)
        if session.expires_at <= now:
            return None

        return session
