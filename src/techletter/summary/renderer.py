"""페이지 렌더링.

브라우저를 **한 번만 띄우고 재사용**한다. 현행은 이벤트마다
`chromium.launch()`/`close()`를 해서 건당 1초 이상을 기동에 썼다(ISSUE-007 #6).

재시도 대기도 줄였다. 현행은 최대 570초를 동기 `time.sleep`으로 기다려
컨슈머 스레드가 멈췄고, 그걸 버티려고 Kafka `max.poll.interval.ms`를 53분으로
늘려 놨다(#5). 여기서는 `asyncio.sleep`이고 상한이 훨씬 낮다.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from techletter.core.errors import PermanentError, RetryableError
from techletter.core.http import BROWSER_USER_AGENT
from techletter.core.logging import get_logger
from techletter.summary.constants import RETRY_MARKERS

if TYPE_CHECKING:  # pragma: no cover
    from types import TracebackType

    import httpx

    from techletter.settings import SummarySettings

__all__ = ["PlaywrightRenderer", "Renderer", "ScraperApiRenderer", "needs_retry"]

logger = get_logger(__name__)

CHROME_PATH_ENV = "CHROME_PATH"
SCRAPERAPI_URL = "https://api.scraperapi.com"
SCRAPERAPI_TIMEOUT = 90.0
# 차단 페이지는 대개 짧다. 긴 문서에서 마커를 찾으면 정상 글의 인용문일 확률이 높다.
RETRY_MARKER_MAX_HTML = 50_000
RETRY_WAIT_SECONDS = (5, 15, 30)


def needs_retry(html: str) -> bool:
    if len(html) > RETRY_MARKER_MAX_HTML:
        return False
    lowered = html.lower()
    return any(marker in lowered for marker in RETRY_MARKERS)


class Renderer(Protocol):
    async def render(self, url: str) -> str: ...

    async def aclose(self) -> None: ...


class ScraperApiRenderer:
    """외부 렌더링 서비스. API 키가 URL에 들어가므로 **https만** 쓴다.

    현행은 `http://api.scraperapi.com`이라 키가 평문으로 나갔다(ISSUE-007 #7).
    """

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._client = client

    async def render(self, url: str) -> str:
        import httpx  # noqa: PLC0415

        try:
            response = await self._client.get(
                SCRAPERAPI_URL,
                params={"api_key": self._api_key, "url": url, "render": "true"},
                timeout=SCRAPERAPI_TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise RetryableError(f"scraperapi request failed: {type(exc).__name__}") from exc

        if response.status_code == 401:
            raise PermanentError("scraperapi rejected the key", reason="scraperapi_auth")
        if response.status_code != 200:
            # 키를 로그에도 예외 메시지에도 남기지 않는다.
            raise RetryableError(f"scraperapi returned HTTP {response.status_code}")
        return response.text

    async def aclose(self) -> None:
        return


class PlaywrightRenderer:
    def __init__(self, settings: SummarySettings) -> None:
        self._settings = settings
        self._playwright: Any = None
        self._browser: Any = None
        self._lock = asyncio.Lock()

    def _launch_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "headless": True,
            "args": [
                f"--user-agent={BROWSER_USER_AGENT}",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-crashpad",
                "--disable-breakpad",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
            ],
        }
        chrome_path = os.getenv(CHROME_PATH_ENV)
        if chrome_path and Path(chrome_path).exists():
            options["executable_path"] = chrome_path
        return options

    async def _get_browser(self) -> Any:
        """브라우저 하나를 띄워 두고 재사용한다. 죽었으면 다시 띄운다."""
        async with self._lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser
            from playwright.async_api import async_playwright  # noqa: PLC0415

            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(**self._launch_options())
            logger.info("browser launched")
            return self._browser

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9,ko-KR,ko;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    @staticmethod
    def _retry_url(url: str, attempt: int) -> str:
        """캐시된 차단 페이지를 다시 받지 않으려고 쿼리를 하나 붙인다."""
        if attempt == 0:
            return url
        return f"{url}{'&' if '?' in url else '?'}_tl_retry={attempt}"

    async def render(self, url: str) -> str:
        browser = await self._get_browser()
        attempts = max(1, self._settings.max_render_attempts)
        timeout_ms = self._settings.render_timeout_seconds * 1000
        last_html = ""

        for attempt in range(attempts):
            # 컨텍스트는 잡마다 새로 만든다. 쿠키가 이월되면 차단이 이어진다.
            context = await browser.new_context(
                user_agent=BROWSER_USER_AGENT,
                locale="en-US",
                extra_http_headers=self._headers(),
            )
            try:
                page = await context.new_page()
                await page.goto(
                    self._retry_url(url, attempt),
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                await page.wait_for_selector("body", timeout=timeout_ms)
                last_html = await page.content()
            except Exception as exc:
                raise RetryableError(f"render failed: {type(exc).__name__}: {exc}") from exc
            finally:
                await context.close()

            if not needs_retry(last_html):
                return last_html

            if attempt + 1 < attempts:
                wait = RETRY_WAIT_SECONDS[min(attempt, len(RETRY_WAIT_SECONDS) - 1)]
                logger.info(
                    "bot challenge; retrying",
                    extra={"url": url, "attempt": attempt + 1, "wait_seconds": wait},
                )
                await asyncio.sleep(wait)

        # 모든 시도가 차단 페이지였다. 잡 큐가 더 긴 간격으로 다시 시도한다.
        raise RetryableError(f"blocked after {attempts} render attempts")

    async def aclose(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def __aenter__(self) -> PlaywrightRenderer:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
