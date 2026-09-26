"""페이지 렌더링.

브라우저를 **한 번만 띄우고 재사용**한다. 재시도 대기는 `asyncio.sleep`을
쓰고 상한이 낮다(`RETRY_WAIT_SECONDS`).

헤드리스 브라우저만 막는 사이트가 있다(Medium: 브라우저는 403, 일반 HTTP는
200). 그래서 차단 페이지가 나오면 브라우저로 다시 시도하기 전에 일반 HTTP로
한 번 받아 본다.
"""

from __future__ import annotations

import asyncio
import base64
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

__all__ = ["PlaywrightRenderer", "Renderer", "needs_retry"]

logger = get_logger(__name__)

CHROME_PATH_ENV = "CHROME_PATH"
# 차단 페이지는 대개 짧다. 긴 문서에서 마커를 찾으면 정상 글의 인용문일 확률이 높다.
RETRY_MARKER_MAX_HTML = 50_000
RETRY_WAIT_SECONDS = (5, 15, 30)
# 없는 페이지. 다시 열어도 같다.
GONE_STATUS = frozenset({404, 410})
# 서버 IP 차단·요청 제한·원 서버 오류. 본문 문구와 상관없이 차단으로 본다
# (삼성은 520 오류 페이지를, Medium은 403 챌린지 페이지를 준다).
BLOCKED_STATUS = frozenset({401, 403, 429})
# 본문을 자바스크립트로 늦게 그리는 페이지(카카오·NHN). 이보다 짧으면 네트워크가
# 잠잠해질 때까지 기다렸다가 다시 읽는다 — 183자였던 카카오 글이 3만 자가 됐다.
SETTLE_MIN_CHARS = 1000
SETTLE_TIMEOUT_MS = 15_000


def is_blocked_status(status: int) -> bool:
    return status in BLOCKED_STATUS or status >= 500


def needs_retry(html: str) -> bool:
    if len(html) > RETRY_MARKER_MAX_HTML:
        return False
    lowered = html.lower()
    return any(marker in lowered for marker in RETRY_MARKERS)


class Renderer(Protocol):
    async def render(self, url: str, *, attempts: int | None = None) -> str: ...

    async def aclose(self) -> None: ...


class PlaywrightRenderer:
    def __init__(
        self, settings: SummarySettings, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._http = http_client
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

    async def _fetch_plain(self, url: str) -> str | None:
        """일반 HTTP로 받는다. 200이고 차단 페이지가 아닐 때만 돌려준다."""
        if self._http is None:
            return None
        try:
            response = await self._http.get(url)
        except Exception:
            logger.info("http fallback failed", extra={"url": url})
            return None
        if response.status_code != 200 or needs_retry(response.text):
            logger.info("http fallback blocked", extra={"url": url, "status": response.status_code})
            return None
        return response.text

    @staticmethod
    async def _settle(page: Any) -> None:
        """본문이 짧으면 네트워크가 잠잠해질 때까지 기다린다. 제한 시간이 지나면 그냥 둔다."""
        length = await page.evaluate("document.body ? document.body.innerText.length : 0")
        if length >= SETTLE_MIN_CHARS:
            return
        try:
            await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
        except Exception:
            logger.info("page did not settle", extra={"chars": length})

    async def render(self, url: str, *, attempts: int | None = None) -> str:
        """`attempts`로 브라우저 재시도 횟수를 줄일 수 있다 — 대체 본문이 있는 쪽이 쓴다."""
        browser = await self._get_browser()
        attempts = max(1, attempts or self._settings.max_render_attempts)
        timeout_ms = self._settings.render_timeout_seconds * 1000
        last_html = ""
        tried_plain = False

        for attempt in range(attempts):
            # 컨텍스트는 잡마다 새로 만든다. 쿠키가 이월되면 차단이 이어진다.
            context = await browser.new_context(
                user_agent=BROWSER_USER_AGENT,
                locale="en-US",
                extra_http_headers=self._headers(),
            )
            try:
                page = await context.new_page()
                response = await page.goto(
                    self._retry_url(url, attempt),
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                status = response.status if response is not None else 200
                if status in GONE_STATUS:
                    raise PermanentError(f"page not found: HTTP {status}", reason="not_found")
                await page.wait_for_selector("body", timeout=timeout_ms)
                if not is_blocked_status(status):
                    await self._settle(page)
                last_html = await page.content()
            except PermanentError:
                raise
            except Exception as exc:
                raise RetryableError(f"render failed: {type(exc).__name__}: {exc}") from exc
            finally:
                await context.close()

            if not (is_blocked_status(status) or needs_retry(last_html)):
                return last_html

            if not tried_plain:
                tried_plain = True
                plain = await self._fetch_plain(url)
                if plain is not None:
                    logger.info("browser blocked; used http fallback", extra={"url": url})
                    return plain

            if attempt + 1 < attempts:
                wait = RETRY_WAIT_SECONDS[min(attempt, len(RETRY_WAIT_SECONDS) - 1)]
                logger.info(
                    "bot challenge; retrying",
                    extra={"url": url, "attempt": attempt + 1, "wait_seconds": wait},
                )
                await asyncio.sleep(wait)

        # 모든 시도가 차단 페이지였다. 잡 큐가 더 긴 간격으로 다시 시도한다.
        raise RetryableError(f"blocked after {attempts} render attempts")

    async def rasterize_svg(self, svg: bytes, size: int = 128) -> bytes | None:
        """SVG를 투명 배경 PNG로 그린다. 아이콘이 SVG뿐인 사이트용(Pillow는 SVG를 못 연다).

        `<img>`로 넣어 그리므로 SVG 안의 스크립트와 외부 리소스는 불러오지 않는다.
        """
        browser = await self._get_browser()
        src = "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
        html = (
            "<style>html,body{margin:0;background:transparent}"
            "img{width:100vw;height:100vh;object-fit:contain;display:block}</style>"
            f'<img src="{src}">'
        )
        context = await browser.new_context(viewport={"width": size, "height": size})
        try:
            page = await context.new_page()
            await page.set_content(html, timeout=10_000)
            loaded = await page.evaluate(
                "() => { const i = document.images[0];"
                " return i.decode().then(() => i.naturalWidth > 0, () => false); }"
            )
            if not loaded:
                return None
            return await page.screenshot(type="png", omit_background=True)
        except Exception as exc:
            logger.info("svg rasterize failed", extra={"error": str(exc)[:200]})
            return None
        finally:
            await context.close()

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
