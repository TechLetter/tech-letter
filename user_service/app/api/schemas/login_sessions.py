from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LoginSessionCreateRequest(BaseModel):
    session_id: str
    jwt_token: str
    expires_at: datetime


class LoginSessionCreateResponse(BaseModel):
    session_id: str


class LoginSessionDeleteResponse(BaseModel):
    jwt_token: str
