"""본문 검증 — 길이와 무관하게 차단 페이지를 걸러낸다."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError
from techletter.summary.constants import (
    BLOCK_MARKERS_SOFT,
    BLOCK_MARKERS_STRONG,
    BLOCK_MARKERS_UNKNOWN,
    RETRY_MARKERS,
)
from techletter.summary.validator import SOFT_MARKER_MAX_LENGTH, validate_plain_text

GOOD = "Kafka 컨슈머 그룹의 리밸런싱은 파티션 재할당 과정에서 " * 5


def test_every_marker_is_lowercase() -> None:
    """대문자가 섞이면 `html.lower()`와 비교할 때 영원히 매칭되지 않는다.

    `RETRY_MARKERS`에 `"Out of nothing, something."`처럼 대문자가 섞인 적이 있다.
    """
    for markers in (
        BLOCK_MARKERS_STRONG,
        BLOCK_MARKERS_UNKNOWN,
        BLOCK_MARKERS_SOFT,
        RETRY_MARKERS,
    ):
        assert all(marker == marker.lower() for marker in markers)


def test_the_marker_that_never_matched_is_now_reachable() -> None:
    assert "out of nothing, something." in RETRY_MARKERS


def test_a_real_article_passes() -> None:
    validate_plain_text(GOOD)


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_text_is_permanent(text: str) -> None:
    with pytest.raises(PermanentError) as excinfo:
        validate_plain_text(text)

    assert excinfo.value.reason == "content_empty"


def test_a_too_short_text_is_permanent() -> None:
    with pytest.raises(PermanentError) as excinfo:
        validate_plain_text("짧다")

    assert excinfo.value.reason == "content_too_short"


def test_a_long_bot_challenge_is_caught() -> None:
    """1000자 이상이면 검사조차 하지 않고 통과시키면 안 된다."""
    page = "Checking your browser. " + ("padding text " * 300) + "verify you are human"

    assert len(page) > 1000
    with pytest.raises(PermanentError) as excinfo:
        validate_plain_text(page)

    assert excinfo.value.reason in {"bot_blocked", "unresolved_page"}


def test_a_long_cloudflare_page_is_caught() -> None:
    page = ("본문처럼 보이는 텍스트 " * 200) + "challenges.cloudflare.com"

    with pytest.raises(PermanentError) as excinfo:
        validate_plain_text(page)

    assert excinfo.value.reason == "bot_blocked"


def test_a_short_error_page_is_caught() -> None:
    with pytest.raises(PermanentError) as excinfo:
        validate_plain_text("404 Not Found. The requested page does not exist here.")

    assert excinfo.value.reason == "error_page"


def test_soft_markers_do_not_block_long_articles() -> None:
    """ "not found" 는 정상 기술 글에도 흔하다."""
    article = "설정 파일이 not found 오류를 낼 때의 대처를 정리한다. " * 40

    assert len(article) > SOFT_MARKER_MAX_LENGTH
    validate_plain_text(article)
