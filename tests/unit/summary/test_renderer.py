"""렌더러 — 재시도 판정과 ScraperAPI 경로."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from techletter.core.errors import PermanentError, RetryableError
from techletter.summary.renderer import (
    RETRY_MARKER_MAX_HTML,
    SCRAPERAPI_URL,
    ScraperApiRenderer,
    needs_retry,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "html"


def test_a_challenge_page_triggers_a_retry() -> None:
    assert needs_retry((FIXTURES / "cloudflare.html").read_text(encoding="utf-8")) is True


def test_a_normal_article_does_not() -> None:
    assert needs_retry((FIXTURES / "article.html").read_text(encoding="utf-8")) is False


def test_markers_are_matched_case_insensitively() -> None:
    """마커 목록이 소문자여야 `html.lower()` 비교가 동작한다."""
    assert needs_retry("<p>VERIFYING YOU ARE HUMAN</p>") is True


def test_the_previously_dead_marker_now_works() -> None:
    assert needs_retry("<p>Out Of Nothing, Something.</p>") is True


def test_long_pages_are_not_treated_as_challenges() -> None:
    """긴 문서에 마커가 있으면 정상 글의 인용문일 확률이 높다."""
    html = "<p>본문</p>" * 20_000 + "just a moment"

    assert len(html) > RETRY_MARKER_MAX_HTML
    assert needs_retry(html) is False


# ── ScraperAPI ──────────────────────────────────────────────────────
def renderer(handler) -> tuple[ScraperApiRenderer, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    return ScraperApiRenderer("secret-key", client), seen


async def test_scraperapi_is_called_over_https() -> None:
    """http로 나가면 API 키가 평문으로 노출된다."""
    render, seen = renderer(lambda r: httpx.Response(200, text="<html>ok</html>"))

    await render.render("https://blog.test/post")

    assert str(seen[0].url).startswith(SCRAPERAPI_URL)
    assert seen[0].url.scheme == "https"


async def test_a_rejected_key_is_permanent() -> None:
    render, _ = renderer(lambda r: httpx.Response(401))

    with pytest.raises(PermanentError) as excinfo:
        await render.render("https://blog.test/post")

    assert excinfo.value.reason == "scraperapi_auth"


async def test_a_server_error_is_retryable() -> None:
    render, _ = renderer(lambda r: httpx.Response(500))

    with pytest.raises(RetryableError):
        await render.render("https://blog.test/post")


async def test_the_api_key_never_appears_in_the_error() -> None:
    render, _ = renderer(lambda r: httpx.Response(500))

    with pytest.raises(RetryableError) as excinfo:
        await render.render("https://blog.test/post")

    assert "secret-key" not in str(excinfo.value)


async def test_a_connection_failure_is_retryable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns", request=request)

    render, _ = renderer(boom)

    with pytest.raises(RetryableError):
        await render.render("https://blog.test/post")
