from __future__ import annotations

from typing import Protocol

from common.models.blog import Blog, ListBlogsFilter
from common.models.post import ListPostsFilter, Post


class PostRepositoryInterface(Protocol):
    """PostRepository가 따라야 할 최소한의 계약.

    Service 레이어는 이 인터페이스에만 의존하고, 구체 구현(Mongo 등)은 몰라도 된다.
    """

    def list(
        self, flt: ListPostsFilter
    ) -> tuple[list[Post], int]:  # pragma: no cover - Protocol
        ...


class BlogRepositoryInterface(Protocol):
    """BlogRepository가 따라야 할 최소한의 계약."""

    def list(
        self, flt: ListBlogsFilter
    ) -> tuple[list[Blog], int]:  # pragma: no cover - Protocol
        ...
