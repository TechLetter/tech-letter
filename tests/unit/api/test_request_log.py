"""요청 로그 — 검색어는 남기지 않는다(개인정보처리방침)."""

from __future__ import annotations

from urllib.parse import quote

from techletter.api.middleware import redact_query


def test_the_search_query_is_masked() -> None:
    raw = f"q={quote('카프카 장애')}&page=2".encode()

    assert redact_query(raw) == "q=***&page=2"


def test_other_queries_are_kept() -> None:
    assert redact_query(b"page=1&page_size=12&categories=AI") == "page=1&page_size=12&categories=AI"


def test_an_empty_query_stays_empty() -> None:
    assert redact_query(b"") == ""
