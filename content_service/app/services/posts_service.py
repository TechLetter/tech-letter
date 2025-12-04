from __future__ import annotations

from fastapi import Depends
from pymongo.database import Database

from common.mongo.client import get_database
from common.models.post import ListPostsFilter, Post
from ..repositories.interfaces import PostRepositoryInterface
from ..repositories.post_repository import PostRepository


class PostsService:
    """포스트 조회/검색 비즈니스 로직.

    - Repository(PostRepository)에만 의존하고, Mongo 세부 구현은 알지 않는다.
    """

    def __init__(self, repo: PostRepositoryInterface) -> None:
        self._repo = repo

    def list_posts(self, filter_: ListPostsFilter) -> tuple[list[Post], int]:
        return self._repo.list(filter_)

    def get_post(self, post_id: str) -> Post | None:
        return self._repo.find_by_id(post_id)

    def get_plain_text(self, post_id: str) -> str | None:
        return self._repo.get_plain_text(post_id)

    def get_rendered_html(self, post_id: str) -> str | None:
        return self._repo.get_rendered_html(post_id)

    def increment_view_count(self, post_id: str) -> bool:
        return self._repo.increment_view_count(post_id)


def get_post_repository(
    db: Database = Depends(get_database),
) -> PostRepositoryInterface:
    """FastAPI DI용 PostRepository 팩토리."""

    return PostRepository(db)


def get_posts_service(
    repo: PostRepository = Depends(get_post_repository),
) -> PostsService:
    """FastAPI DI용 PostsService 팩토리."""

    return PostsService(repo)
