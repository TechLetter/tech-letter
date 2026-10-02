"""질문에서 범위를 코드로 읽는다 — 기준선에서 LLM 플래너가 틀린 질문들."""

from __future__ import annotations

from datetime import datetime

import pytest

from techletter.chat.agent.scope import KST, BlogRef, is_reference, parse_period, read_scope

BLOGS = [
    BlogRef("b-kakao", "카카오"),
    BlogRef("b-toss", "토스"),
    BlogRef("b-line", "라인"),
    BlogRef("b-aws", "AWS"),
    BlogRef("b-daangn", "당근마켓"),
    BlogRef("b-kakaopay", "카카오페이"),
]
NOW = datetime(2026, 9, 27, 15, 0, tzinfo=KST)


def scope(query: str):
    return read_scope(query, BLOGS, NOW)


def test_the_service_name_is_not_a_blog() -> None:
    """기준선 q04: 플래너가 "Tech-Letter"를 블로그로 읽고 태그를 지어내 0건이었다."""
    s = scope("Tech-Letter에 있는 글 기준으로 MSA vs 모놀리스 비교해줘")

    assert s.blog is None
    assert s.boost_blog is None
    assert s.is_list is False


def test_a_named_blog_narrows_the_list() -> None:
    """기준선 q06: "카카오 블로그"를 그대로 찾아 0건이었다."""
    s = scope("카카오 블로그 글 목록 보여줘")

    assert s.blog == BlogRef("b-kakao", "카카오")
    assert s.is_list is True


def test_a_bare_blog_name_only_boosts() -> None:
    """기준선 q07: 없는 태그를 AND로 걸어 0건이었다. 이름만 나오면 좁히지 않는다."""
    s = scope("토스 결제 시스템 글 정리해줘")

    assert s.blog is None
    assert s.boost_blog == BlogRef("b-toss", "토스")
    assert s.is_list is False


@pytest.mark.parametrize("query", ["데이터 파이프라인 설계 사례", "가이드라인 알려줘"])
def test_words_containing_a_blog_name_are_not_blogs(query: str) -> None:
    s = scope(query)

    assert s.blog is None
    assert s.boost_blog is None


def test_a_technology_name_does_not_narrow() -> None:
    assert scope("AWS Lambda 콜드 스타트 줄인 사례").blog is None


def test_the_longest_blog_name_wins() -> None:
    assert scope("카카오페이 블로그 글").blog == BlogRef("b-kakaopay", "카카오페이")


def test_an_alias_names_a_blog() -> None:
    assert scope("당근 블로그에 올라온 글").blog == BlogRef("b-daangn", "당근마켓")


def test_a_period_with_a_topic_list() -> None:
    s = scope("이번 달 쿠버네티스 카테고리 글 목록")

    assert s.is_list is True
    assert s.published_from == datetime(2026, 9, 1, tzinfo=KST)
    assert "쿠버네티스·컨테이너" in s.topics


def test_a_count_limits_the_list() -> None:
    s = scope("최근 글 5개 보여줘")

    assert s.is_list is True
    assert s.limit == 5


def test_asking_for_an_explanation_is_not_a_list() -> None:
    assert scope("MCP 서버 도입 사례 글 알려줘 어떻게 했는지").is_list is False


@pytest.mark.parametrize(
    ("query", "start", "end_day"),
    [
        ("지난달 글", datetime(2026, 8, 1, tzinfo=KST), 31),
        ("지난주 글", datetime(2026, 9, 14, tzinfo=KST), 20),
        ("2025년 3월 글", datetime(2025, 3, 1, tzinfo=KST), 31),
        ("11월 글", datetime(2025, 11, 1, tzinfo=KST), 30),
    ],
)
def test_periods_are_kst_calendar_ranges(query: str, start: datetime, end_day: int) -> None:
    got_start, got_end, _ = parse_period(query, NOW)

    assert got_start == start
    assert got_end is not None
    assert got_end.astimezone(KST).day == end_day


def test_no_period_is_none() -> None:
    assert parse_period("Kafka 리밸런싱", NOW) == (None, None, "")


@pytest.mark.parametrize(
    "query", ["거기서 KV 캐시는 어떻게 다뤘어?", "그 글에서 보안은?", "두 번째 방식 자세히"]
)
def test_references_point_at_the_previous_answer(query: str) -> None:
    assert is_reference(query)


def test_asking_for_other_posts_releases_the_reference() -> None:
    assert not is_reference("그중 말고 다른 글도 알려줘")


def test_an_unknown_blog_is_reported() -> None:
    """평가 q25: 모으지 않는 블로그를 물으면 엉뚱한 글을 나열하지 않는다."""
    s = scope("우아한형제들(배민) 블로그에 올라온 글 목록 보여줘")

    assert s.blog is None
    assert s.unknown_blog == "우아한형제들"


def test_a_known_blog_is_never_unknown() -> None:
    assert scope("카카오 블로그 글").unknown_blog == ""


def test_named_blogs_to_skip_are_excluded_not_boosted() -> None:
    """평가 q26: "카카오, 당근마켓 말고"에서 당근마켓 글을 오히려 올렸다."""
    s = scope("그 두 회사(카카오, 당근마켓) 말고 다른 회사들의 CDC 사례도 보여줘")

    assert s.boost_blog is None
    assert {b.name for b in s.exclude_blogs} == {"카카오", "당근마켓"}
    assert not is_reference("그 두 회사(카카오, 당근마켓) 말고 다른 회사들의 CDC 사례도 보여줘")
