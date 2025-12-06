from __future__ import annotations

from datetime import datetime, timezone

from common.mongo.types import (
    BaseDocument,
    MongoDateTime,
    build_document_data_from_domain,
)
from ...models.login_session import LoginSession


class LoginSessionDocument(BaseDocument):
    """MongoDB login_sessions 컬렉션 도큐먼트 모델."""

    session_id: str
    jwt_token: str
    expires_at: MongoDateTime

    @classmethod
    def from_domain(cls, session: LoginSession) -> "LoginSessionDocument":
        # LoginSession 도메인 모델이 created_at / updated_at 을 모두 갖고 있으므로
        # 공통 유틸을 통해 그대로 직렬화한다.
        data = build_document_data_from_domain(session)
        return cls.model_validate(data)

    def to_domain(self) -> LoginSession:
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
        return LoginSession(
            session_id=self.session_id,
            jwt_token=self.jwt_token,
            expires_at=self.expires_at,
            created_at=created_at,
            updated_at=updated_at,
        )
