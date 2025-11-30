from __future__ import annotations

from fastapi import Depends
from pymongo.database import Database

from common.mongo.client import get_database
from common.models.blog import Blog, ListBlogsFilter
from app.repositories.blog_repository import BlogRepository
from app.repositories.interfaces import BlogRepositoryInterface


class BlogsService:
    """블로그 목록 조회 비즈니스 로직.

    - Repository(BlogRepository)에만 의존하고, Mongo 세부 구현은 알지 않는다.
    """

    def __init__(self, repo: BlogRepositoryInterface) -> None:
        self._repo = repo

    def list_blogs(self, filter_: ListBlogsFilter) -> tuple[list[Blog], int]:
        return self._repo.list(filter_)


def get_blog_repository(
    db: Database = Depends(get_database),
) -> BlogRepositoryInterface:
    """FastAPI DI용 BlogRepository 팩토리."""

    return BlogRepository(db)


def get_blogs_service(
    repo: BlogRepository = Depends(get_blog_repository),
) -> BlogsService:
    """FastAPI DI용 BlogsService 팩토리."""

    return BlogsService(repo)
