"""포스트 목록 쿼리 조립."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from techletter.content.models import ListPostsFilter
from techletter.content.repositories import PostRepository

build = PostRepository.build_query


def test_no_filter_is_an_empty_query() -> None:
    assert build(ListPostsFilter()) == {}


def test_categories_and_tags_together_are_a_union() -> None:
    """교집합으로 바꾸면 프론트 필터 결과가 통째로 달라진다."""
    query = build(ListPostsFilter(categories=["Backend"], tags=["Kafka"]))

    assert set(query) == {"$or"}
    assert len(query["$or"]) == 2


def test_only_categories_uses_a_direct_field() -> None:
    query = build(ListPostsFilter(categories=["Backend"]))

    assert "$or" not in query
    assert "aisummary.categories" in query


def test_names_match_case_insensitively_but_exactly() -> None:
    (pattern,) = build(ListPostsFilter(tags=["Kafka"]))["aisummary.tags"]["$in"]

    assert isinstance(pattern, re.Pattern)
    assert pattern.match("kafka") and pattern.match("KAFKA")
    assert not pattern.match("kafka-connect")  # 부분 일치는 아니다


def test_regex_metacharacters_in_a_tag_are_escaped() -> None:
    (pattern,) = build(ListPostsFilter(tags=["C++"]))["aisummary.tags"]["$in"]

    assert pattern.match("c++")
    assert not pattern.match("c")


def test_blank_names_are_dropped() -> None:
    assert build(ListPostsFilter(tags=["  ", ""])) == {}


def test_invalid_blog_id_matches_nothing_instead_of_raising() -> None:
    query = build(ListPostsFilter(blog_id="not-an-object-id"))

    assert query["blog_id"] == {"$in": []}


def test_published_range() -> None:
    query = build(
        ListPostsFilter(
            published_from=datetime(2025, 1, 1, tzinfo=UTC),
            published_to=datetime(2025, 2, 1, tzinfo=UTC),
        )
    )

    assert set(query["published_at"]) == {"$gte", "$lte"}


def test_summarized_true_is_a_plain_equality() -> None:
    assert build(ListPostsFilter(summarized=True))["status.ai_summarized"] is True


def test_summarized_false_also_matches_documents_missing_the_field() -> None:
    """오래된 포스트에는 status 하위 필드가 아예 없다."""
    (condition,) = build(ListPostsFilter(summarized=False))["$and"]

    assert condition == {
        "$or": [
            {"status.ai_summarized": False},
            {"status.ai_summarized": {"$exists": False}},
        ]
    }


def test_search_covers_title_and_blog_name() -> None:
    (condition,) = build(ListPostsFilter(search="kafka"))["$and"]

    assert [next(iter(clause)) for clause in condition["$or"]] == ["title", "blog_name"]


def test_search_escapes_metacharacters() -> None:
    (condition,) = build(ListPostsFilter(search="a.b"))["$and"]

    assert condition["$or"][0]["title"]["$regex"] == r"a\.b"
