from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatSuggestedQuestion(BaseModel):
    id: Optional[str] = None
    text: str = Field(..., min_length=1, max_length=500)
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
