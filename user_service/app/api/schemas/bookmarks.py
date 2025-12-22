from __future__ import annotations

from pydantic import BaseModel

from common.types.datetime import UtcDateTime


class BookmarkCreateRequest(BaseModel):
    user_code: str
    post_id: str


class BookmarkItem(BaseModel):
    post_id: str
    created_at: UtcDateTime


# ListBookmarksResponse 대신 common.schemas.pagination.PaginatedResponse[BookmarkItem] 사용


class BookmarkCheckRequest(BaseModel):
    user_code: str
    post_ids: list[str]


class BookmarkCheckResponse(BaseModel):
    bookmarked_post_ids: list[str]
