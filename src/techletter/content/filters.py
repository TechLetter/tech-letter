"""필터 통계.

**필터가 걸리면 전체 목록을 기준으로 삼고, 필터 결과에 없는 항목은
`count=0`으로 남긴다.** 프론트가 체크박스 목록을 그대로 유지한 채
개수만 바꾸는 UI라서 그렇다.

"전체 목록"은 blog_id를 무시한다. 즉 블로그를 고르면 그 블로그에
없는 태그도 `count=0`으로 계속 보인다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.repositories import PostRepository

__all__ = ["BlogFilterItem", "FilterItem", "FiltersService"]


@dataclass(frozen=True, slots=True)
class FilterItem:
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class BlogFilterItem:
    blog_id: str
    name: str
    count: int


def _sorted_items(counts: dict[str, int]) -> list[FilterItem]:
    """개수 내림차순, 같으면 이름 오름차순(대소문자 무시)."""
    return [
        FilterItem(name=name, count=count)
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    ]


class FiltersService:
    def __init__(self, posts: PostRepository) -> None:
        self._posts = posts

    async def categories(self, blog_id: str | None, tags: list[str]) -> list[FilterItem]:
        if not blog_id and not tags:
            return _sorted_items(await self._posts.category_counts(None, []))
        every = await self._posts.category_counts(None, [])
        matched = await self._posts.category_counts(blog_id, tags)
        return _sorted_items({name: matched.get(name, 0) for name in every})

    async def tags(self, blog_id: str | None, categories: list[str]) -> list[FilterItem]:
        if not blog_id and not categories:
            return _sorted_items(await self._posts.tag_counts(None, []))
        every = await self._posts.tag_counts(None, [])
        matched = await self._posts.tag_counts(blog_id, categories)
        return _sorted_items({name: matched.get(name, 0) for name in every})

    async def blogs(self, categories: list[str], tags: list[str]) -> list[BlogFilterItem]:
        every = await self._posts.blog_counts([], [])
        if not categories and not tags:
            rows = every
        else:
            filtered = await self._posts.blog_counts(categories, tags)
            matched = {blog_id: count for blog_id, _, count in filtered}
            rows = [(blog_id, name, matched.get(blog_id, 0)) for blog_id, name, _ in every]
        rows.sort(key=lambda row: (-row[2], row[1].lower()))
        return [BlogFilterItem(blog_id=b, name=n, count=c) for b, n, c in rows]
