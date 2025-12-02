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

    def is_exist_by_link(self, link: str) -> bool:  # pragma: no cover - Protocol
        ...

    def insert(self, post: Post) -> str:  # pragma: no cover - Protocol
        ...

    def find_by_id(self, id_value: str) -> Post | None:  # pragma: no cover - Protocol
        ...

    def get_plain_text(
        self, id_value: str
    ) -> str | None:  # pragma: no cover - Protocol
        ...

    def get_rendered_html(
        self, id_value: str
    ) -> str | None:  # pragma: no cover - Protocol
        ...

    def update_fields(
        self, id_value: str, updates: dict
    ) -> None:  # pragma: no cover - Protocol
        ...


class BlogRepositoryInterface(Protocol):
    """BlogRepository가 따라야 할 최소한의 계약."""

    def list(
        self, flt: ListBlogsFilter
    ) -> tuple[list[Blog], int]:  # pragma: no cover - Protocol
        ...

    def upsert_by_rss_url(self, blog: Blog) -> str:  # pragma: no cover - Protocol
        ...

    def get_by_rss_url(
        self, rss_url: str
    ) -> Blog | None:  # pragma: no cover - Protocol
        ...
