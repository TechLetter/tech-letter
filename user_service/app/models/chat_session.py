from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatRole(str, Enum):
    """채팅 메시지 역할."""

    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] | None = None


class ChatSessionMemory(BaseModel):
    summary: str = ""
    covered_message_count: int = 0
    status: str = "completed"
    requested_at: datetime | None = None
    updated_at: datetime | None = None
    error_message: str | None = None


class ChatSession(BaseModel):
    id: Optional[str] = None
    user_code: str
    title: str
    messages: List[ChatMessage] = Field(default_factory=list)
    memory: ChatSessionMemory | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
