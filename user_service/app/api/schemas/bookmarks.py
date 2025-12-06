from __future__ import annotations

from pydantic import BaseModel

from common.types.datetime import UtcDateTime


class BookmarkCreateRequest(BaseModel):
    user_code: str
    post_id: str


class BookmarkItem(BaseModel):
    post_id: str
    created_at: UtcDateTime


class ListBookmarksResponse(BaseModel):
    total: int
    items: list[BookmarkItem]


class BookmarkCheckRequest(BaseModel):
    user_code: str
    post_ids: list[str]


class BookmarkCheckResponse(BaseModel):
    bookmarked_post_ids: list[str]
