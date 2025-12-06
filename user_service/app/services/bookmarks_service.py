from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends
from pymongo.database import Database

from common.mongo.client import get_database

from ..models.bookmark import Bookmark
from ..repositories.bookmark_repository import BookmarkRepository
from ..repositories.interfaces import BookmarkRepositoryInterface


class BookmarksService:
    """유저 북마크 관리 비즈니스 로직.

    - Repository(BookmarkRepositoryInterface)에만 의존하고, Mongo 세부 구현은 알지 않는다.
    """

    def __init__(self, repo: BookmarkRepositoryInterface) -> None:
        self._repo = repo

    def add_bookmark(self, user_code: str, post_id: str) -> Bookmark:
        """user_code + post_id 조합으로 북마크를 생성한다.

        이미 존재하는 경우에도 에러 없이 동일 엔티티를 반환한다.
        """

        return self._repo.create(user_code=user_code, post_id=post_id)

    def remove_bookmark(self, user_code: str, post_id: str) -> bool:
        """특정 포스트 북마크를 삭제한다.

        삭제된 경우 True, 존재하지 않았으면 False 를 반환한다.
        """

        return self._repo.delete(user_code=user_code, post_id=post_id)

    def list_bookmarks(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list[Bookmark], int]:
        """유저의 북마크 목록을 페이지네이션하여 반환한다."""

        return self._repo.list_by_user(
            user_code=user_code, page=page, page_size=page_size
        )

    def get_bookmarked_post_ids(self, user_code: str, post_ids: list[str]) -> list[str]:
        """주어진 post_ids 중 해당 유저가 북마크한 post_id 목록만 반환한다."""

        return self._repo.list_post_ids_for_user(user_code=user_code, post_ids=post_ids)


def get_bookmark_repository(
    db: Database = Depends(get_database),
) -> BookmarkRepositoryInterface:
    """FastAPI DI용 BookmarkRepository 팩토리."""

    return BookmarkRepository(db)


def get_bookmarks_service(
    repo: BookmarkRepositoryInterface = Depends(get_bookmark_repository),
) -> BookmarksService:
    """FastAPI DI용 BookmarksService 팩토리."""

    return BookmarksService(repo)
