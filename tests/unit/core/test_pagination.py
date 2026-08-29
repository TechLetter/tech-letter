"""관용적 쿼리 파싱 — 현행 gin 동작을 재현해야 한다.

골든 스냅샷(`tests/contract/snapshots/current/posts__bad_page.json`)에서
`page=abc&page_size=xyz` 요청이 422가 아니라 200을 반환하는 것이 확인됐다.
"""

from __future__ import annotations

import pytest

from techletter.core.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Page,
    lenient_bool,
    lenient_int,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 7),
        ("", 7),
        ("   ", 7),
        ("abc", 7),
        ("12.5", 7),
        ("3", 3),
        (" 3 ", 3),
        (3, 3),
        ("-1", 1),  # 파싱은 되고 minimum으로 잘린다
    ],
)
def test_lenient_int_falls_back_to_default(raw, expected):
    assert lenient_int(raw, default=7, minimum=1) == expected


def test_lenient_int_clamps_range():
    assert lenient_int("0", default=20, minimum=1) == 1
    assert lenient_int("9999", default=20, minimum=1, maximum=100) == 100


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
        (None, None),
        ("", None),
        ("maybe", None),
        ("2", None),
        (True, True),
        (False, False),
    ],
)
def test_lenient_bool(raw, expected):
    assert lenient_bool(raw) is expected


def test_page_parse_defaults():
    page = Page.parse(None, None)
    assert page.page == 1
    assert page.page_size == DEFAULT_PAGE_SIZE


def test_page_parse_garbage_does_not_raise():
    page = Page.parse("abc", "xyz")
    assert (page.page, page.page_size) == (1, DEFAULT_PAGE_SIZE)


def test_page_parse_respects_custom_default_size():
    # 트렌드 포스트 목록은 기본 10이다(04 §4.1).
    assert Page.parse(None, None, default_size=10).page_size == 10


def test_page_size_is_capped():
    assert Page.parse("1", "5000").page_size == MAX_PAGE_SIZE


def test_skip_and_total_pages():
    page = Page(page=3, page_size=20)
    assert page.skip == 40
    assert page.total_pages(137) == 7
    assert page.total_pages(0) == 0
    assert page.total_pages(20) == 1
    assert page.total_pages(21) == 2
