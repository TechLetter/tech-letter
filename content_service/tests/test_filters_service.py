from __future__ import annotations

from typing import Any

import pytest

from content_service.app.services.filters_service import FiltersService
from content_service.app.repositories.interfaces import PostRepositoryInterface


class FakePostRepository(PostRepositoryInterface):
    """FiltersService 정렬 로직 테스트를 위한 가짜 PostRepository 구현."""

    def __init__(self) -> None:
        self._category_stats_no_filter = {"b": 5, "A": 2, "c": 1}
        self._tag_stats_no_filter = {"TagB": 3, "taga": 2, "TagC": 1}
        self._blog_stats_no_filter = [
            ("id2", "BlogB", 3),
            ("id1", "bloga", 5),
            ("id3", "BlogC", 1),
        ]

    # 아래 메서드들은 FiltersService 정렬 테스트에서 사용하지 않지만,
    # 인터페이스를 만족시키기 위해 정의만 해 둔다.
    def list(self, flt: Any) -> tuple[list[Any], int]:  # type: ignore[override]
        raise NotImplementedError

    def is_exist_by_link(self, link: str) -> bool:  # type: ignore[override]
        raise NotImplementedError

    def insert(self, post: Any) -> str:  # type: ignore[override]
        raise NotImplementedError

    def find_by_id(self, id_value: str) -> Any | None:  # type: ignore[override]
        raise NotImplementedError

    def get_plain_text(self, id_value: str) -> str | None:  # type: ignore[override]
        raise NotImplementedError

    def get_rendered_html(self, id_value: str) -> str | None:  # type: ignore[override]
        raise NotImplementedError

    def increment_view_count(self, id_value: str) -> bool:  # type: ignore[override]
        raise NotImplementedError

    def update_fields(self, id_value: str, updates: dict) -> None:  # type: ignore[override]
        raise NotImplementedError

    def get_category_stats(
        self, blog_id: str | None, tags: list[str]
    ) -> dict[str, int]:  # type: ignore[override]
        if blog_id is None and not tags:
            return self._category_stats_no_filter
        return {"b": 1}

    def get_tag_stats(
        self, blog_id: str | None, categories: list[str]
    ) -> dict[str, int]:  # type: ignore[override]
        if blog_id is None and not categories:
            return self._tag_stats_no_filter
        return {"TagB": 1}

    def get_blog_stats(
        self, categories: list[str], tags: list[str]
    ) -> list[tuple[str, str, int]]:  # type: ignore[override]
        if not categories and not tags:
            return self._blog_stats_no_filter
        return [("id2", "BlogB", 1)]


@pytest.fixture
def service() -> FiltersService:
    repo = FakePostRepository()
    return FiltersService(repo)


def test_get_category_filters_sorted_by_name_then_count(
    service: FiltersService,
) -> None:
    # when
    result = service.get_category_filters(blog_id=None, tags=[])

    # then: 이름(대소문자 무시) 기준으로 정렬되어야 한다.
    names = [name for name, _ in result]
    assert names == ["b", "A", "c"]


def test_get_tag_filters_sorted_by_name_then_count(service: FiltersService) -> None:
    # when
    result = service.get_tag_filters(blog_id=None, categories=[])

    # then: 이름(대소문자 무시) 기준으로 정렬되어야 한다.
    names = [name for name, _ in result]
    assert names == ["TagB", "taga", "TagC"]


def test_get_blog_filters_sorted_by_name_then_count(service: FiltersService) -> None:
    # when
    result = service.get_blog_filters(categories=[], tags=[])

    # then: 블로그 이름(대소문자 무시) 기준으로 정렬되어야 한다.
    names = [name for _, name, _ in result]
    assert names == ["bloga", "BlogB", "BlogC"]
