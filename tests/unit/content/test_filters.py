"""필터 통계 병합 규칙."""

from __future__ import annotations

from techletter.content.filters import FiltersService


class FakePosts:
    """호출 인자에 따라 미리 정한 결과를 돌려주는 저장소 대역."""

    def __init__(
        self,
        *,
        every: dict[str, int] | None = None,
        filtered: dict[str, int] | None = None,
        blogs_every: list[tuple[str, str, int]] | None = None,
        blogs_filtered: list[tuple[str, str, int]] | None = None,
    ) -> None:
        self.every = every or {}
        self.filtered = filtered or {}
        self.blogs_every = blogs_every or []
        self.blogs_filtered = blogs_filtered or []
        self.calls = 0

    async def category_counts(self, blog_id, names):
        self.calls += 1
        return self.every if not blog_id and not names else self.filtered

    async def tag_counts(self, blog_id, names):
        self.calls += 1
        return self.every if not blog_id and not names else self.filtered

    async def blog_counts(self, categories, tags):
        self.calls += 1
        return self.blogs_every if not categories and not tags else self.blogs_filtered


async def test_unfiltered_returns_actual_counts_with_one_query() -> None:
    posts = FakePosts(every={"Backend": 3, "AI": 5})

    items = await FiltersService(posts).categories(None, [])  # type: ignore[arg-type]

    assert [(i.name, i.count) for i in items] == [("AI", 5), ("Backend", 3)]
    assert posts.calls == 1


async def test_sorted_by_count_desc_then_name_case_insensitive() -> None:
    posts = FakePosts(every={"redis": 2, "Backend": 2, "AI": 9})

    items = await FiltersService(posts).categories(None, [])  # type: ignore[arg-type]

    assert [i.name for i in items] == ["AI", "Backend", "redis"]


async def test_filtered_keeps_every_name_with_zero_count() -> None:
    """프론트는 체크박스 목록을 유지한 채 개수만 바꾼다."""
    posts = FakePosts(every={"Backend": 3, "AI": 5, "Infra": 1}, filtered={"AI": 2})

    items = await FiltersService(posts).categories("507f1f77bcf86cd799439011", [])  # type: ignore[arg-type]

    assert [(i.name, i.count) for i in items] == [("AI", 2), ("Backend", 0), ("Infra", 0)]


async def test_names_absent_from_the_full_list_are_not_invented() -> None:
    posts = FakePosts(every={"Backend": 3}, filtered={"Backend": 1, "Ghost": 7})

    items = await FiltersService(posts).tags("507f1f77bcf86cd799439011", [])  # type: ignore[arg-type]

    assert [i.name for i in items] == ["Backend"]


async def test_blog_filters_merge_on_id_and_sort_by_name() -> None:
    posts = FakePosts(
        blogs_every=[("b1", "Alpha", 4), ("b2", "beta", 4), ("b3", "Gamma", 9)],
        blogs_filtered=[("b3", "Gamma", 2)],
    )

    items = await FiltersService(posts).blogs(["AI"], [])  # type: ignore[arg-type]

    assert [(i.blog_id, i.count) for i in items] == [("b3", 2), ("b1", 0), ("b2", 0)]
