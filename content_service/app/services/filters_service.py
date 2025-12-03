from __future__ import annotations

from fastapi import Depends
from pymongo.database import Database

from app.repositories.interfaces import PostRepositoryInterface
from app.repositories.post_repository import PostRepository
from common.mongo.client import get_database


class FiltersService:
    """필터 통계 조회 비즈니스 로직"""

    def __init__(self, repo: PostRepositoryInterface) -> None:
        self._repo = repo

    def get_category_filters(
        self, blog_id: str | None, tags: list[str]
    ) -> list[tuple[str, int]]:
        """카테고리 필터 목록을 조회한다.

        검색 조건이 없으면 실제 통계만 반환.
        검색 조건이 있으면 전체 목록을 가져와서 결과에 없는 항목은 count=0으로 설정.
        """
        # 검색 조건이 없을 때
        if not blog_id and not tags:
            stats = self._repo.get_category_stats(None, [])
            return [(name, count) for name, count in stats.items()]

        # 검색 조건이 있을 때: 전체 카테고리 목록 조회
        all_categories = self._repo.get_category_stats(None, [])
        # 검색 결과 조회
        filtered_stats = self._repo.get_category_stats(blog_id, tags)

        # 병합: 결과에 없는 항목은 count=0
        result = []
        for cat_name in all_categories.keys():
            count = filtered_stats.get(cat_name, 0)
            result.append((cat_name, count))

        return result

    def get_tag_filters(
        self, blog_id: str | None, categories: list[str]
    ) -> list[tuple[str, int]]:
        """태그 필터 목록을 조회한다."""
        if not blog_id and not categories:
            stats = self._repo.get_tag_stats(None, [])
            return [(name, count) for name, count in stats.items()]

        all_tags = self._repo.get_tag_stats(None, [])
        filtered_stats = self._repo.get_tag_stats(blog_id, categories)

        result = []
        for tag_name in all_tags.keys():
            count = filtered_stats.get(tag_name, 0)
            result.append((tag_name, count))

        return result

    def get_blog_filters(
        self, categories: list[str], tags: list[str]
    ) -> list[tuple[str, str, int]]:
        """블로그 필터 목록을 조회한다. (blog_id, blog_name, count)"""
        if not categories and not tags:
            return self._repo.get_blog_stats([], [])

        # 전체 블로그 목록 조회
        all_blogs = self._repo.get_blog_stats([], [])
        all_blogs_dict = {blog_id: blog_name for blog_id, blog_name, _ in all_blogs}

        # 검색 결과 조회
        filtered_blogs = self._repo.get_blog_stats(categories, tags)
        filtered_dict = {blog_id: count for blog_id, _, count in filtered_blogs}

        # 병합
        result = []
        for blog_id, blog_name in all_blogs_dict.items():
            count = filtered_dict.get(blog_id, 0)
            result.append((blog_id, blog_name, count))

        return result


def get_filters_service(
    db: Database = Depends(get_database),
) -> FiltersService:
    """FastAPI DI용 FiltersService 팩토리"""
    repo = PostRepository(db)
    return FiltersService(repo)
