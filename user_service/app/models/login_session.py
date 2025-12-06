from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator


class LoginSession(BaseModel):
    """JWT를 일시적으로 보관하는 로그인 세션 도메인 모델.

    - session_id는 Gateway와 프론트 간에만 노출된다.
    - jwt_token은 최대 60초 동안만 저장되며, TTL 인덱스로 자동 삭제된다.
    """

    session_id: str
    jwt_token: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("session_id", "jwt_token")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def _validate_expiry(self) -> "LoginSession":
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be greater than created_at")
        return self
