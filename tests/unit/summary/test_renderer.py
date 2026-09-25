"""렌더러 — 차단 페이지 재시도 판정."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from techletter.settings import SummarySettings
from techletter.summary.renderer import (
    RETRY_MARKER_MAX_HTML,
    PlaywrightRenderer,
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


MEDIUM_BLOCK = (
    "<html><title>Attention Required! | Cloudflare</title>"
    "<p>Sorry, you have been blocked</p></html>"
)
ARTICLE = (FIXTURES / "article.html").read_text(encoding="utf-8")


def test_the_medium_block_page_triggers_a_retry() -> None:
    """Medium이 헤드리스 브라우저에 주는 403 페이지. 구체적인 문구로 잡는다."""
    assert needs_retry(MEDIUM_BLOCK) is True


class FakePage:
    """`late_html`이 있으면 네트워크 대기 뒤에야 본문이 그려지는 페이지다."""

    def __init__(self, browser: FakeBrowser) -> None:
        self._browser = browser
        self._html = browser.html

    async def goto(self, *_: Any, **__: Any) -> SimpleNamespace:
        return SimpleNamespace(status=self._browser.status)

    async def wait_for_selector(self, *_: Any, **__: Any) -> None:
        return None

    async def evaluate(self, _: str) -> int:
        return len(self._html)

    async def wait_for_load_state(self, *_: Any, **__: Any) -> None:
        self._browser.settled += 1
        if self._browser.late_html is not None:
            self._html = self._browser.late_html

    async def content(self) -> str:
        return self._html


class FakeContext:
    def __init__(self, browser: FakeBrowser) -> None:
        self._browser = browser

    async def new_page(self) -> FakePage:
        return FakePage(self._browser)

    async def close(self) -> None:
        return None


class FakeBrowser:
    def __init__(self, html: str, status: int = 200, late_html: str | None = None) -> None:
        self.html = html
        self.status = status
        self.late_html = late_html
        self.contexts = 0
        self.settled = 0

    async def new_context(self, **_: Any) -> FakeContext:
        self.contexts += 1
        return FakeContext(self)


def _renderer(
    browser_html: str,
    handler: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: int = 200,
    late_html: str | None = None,
):
    settings = SummarySettings(_env_file=None, max_render_attempts=3)  # pyright: ignore[reportCallIssue]
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    renderer = PlaywrightRenderer(settings, client)
    browser = FakeBrowser(browser_html, status, late_html)

    async def get_browser() -> FakeBrowser:
        return browser

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(renderer, "_get_browser", get_browser)
    monkeypatch.setattr("techletter.summary.renderer.asyncio.sleep", no_sleep)
    return renderer, browser


async def test_a_blocked_browser_falls_back_to_plain_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Medium은 브라우저에 403, 일반 HTTP에는 200을 준다."""
    renderer, browser = _renderer(
        MEDIUM_BLOCK, lambda _: httpx.Response(200, text=ARTICLE), monkeypatch
    )

    assert await renderer.render("https://example.com/post") == ARTICLE
    assert browser.contexts == 1  # 브라우저 재시도 없이 끝났다


async def test_a_blocked_fallback_keeps_retrying_the_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from techletter.core.errors import RetryableError

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403, text=MEDIUM_BLOCK)

    renderer, browser = _renderer(MEDIUM_BLOCK, handler, monkeypatch)

    with pytest.raises(RetryableError, match="blocked after 3"):
        await renderer.render("https://example.com/post")
    assert browser.contexts == 3
    assert len(calls) == 1  # 일반 HTTP는 한 번만 시도한다


async def test_an_unblocked_page_never_touches_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("should not be called")

    renderer, _ = _renderer(ARTICLE, handler, monkeypatch)

    assert await renderer.render("https://example.com/post") == ARTICLE


def _no_http(_: httpx.Request) -> httpx.Response:
    raise AssertionError("should not be called")


async def test_an_error_status_counts_as_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """삼성은 서버 IP에 520을 준다. 오류 페이지 문구가 마커에 없어도 막힌 것이다."""
    from techletter.core.errors import RetryableError

    renderer, browser = _renderer(
        ARTICLE, lambda _: httpx.Response(520, text="origin error"), monkeypatch, status=520
    )

    with pytest.raises(RetryableError, match="blocked"):
        await renderer.render("https://example.com/post")
    assert browser.contexts == 3


async def test_a_missing_page_fails_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from techletter.core.errors import PermanentError

    renderer, browser = _renderer(ARTICLE, _no_http, monkeypatch, status=404)

    with pytest.raises(PermanentError) as excinfo:
        await renderer.render("https://example.com/post")
    assert excinfo.value.reason == "not_found"
    assert browser.contexts == 1


async def test_a_late_rendering_page_is_read_after_it_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """카카오 글은 처음엔 183자, 네트워크가 잠잠해진 뒤엔 3만 자였다."""
    renderer, browser = _renderer("<p>로딩</p>", _no_http, monkeypatch, late_html=ARTICLE)

    assert await renderer.render("https://example.com/post") == ARTICLE
    assert browser.settled == 1


async def test_a_long_page_does_not_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    long_article = ARTICLE + "<p>" + "본문 " * 600 + "</p>"
    renderer, browser = _renderer(long_article, _no_http, monkeypatch)

    await renderer.render("https://example.com/post")
    assert browser.settled == 0


async def test_the_caller_can_cap_browser_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    from techletter.core.errors import RetryableError

    renderer, browser = _renderer(
        MEDIUM_BLOCK, lambda _: httpx.Response(403), monkeypatch, status=403
    )

    with pytest.raises(RetryableError):
        await renderer.render("https://example.com/post", attempts=1)
    assert browser.contexts == 1
