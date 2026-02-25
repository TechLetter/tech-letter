from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import sync_playwright

from .constants import RETRY_MARKERS
from .exceptions import RenderingError

if TYPE_CHECKING:
    from summary_worker.app.config import AppConfig

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
CHROME_PATH_ENV = "CHROME_PATH"
MAX_RENDER_ATTEMPTS = 5
SCRAPERAPI_TIMEOUT = 90
MIN_RETRY_WAIT_SECONDS = 15


class BaseRenderer(ABC):
    @abstractmethod
    def render(self, url: str) -> str:
        """URL의 HTML 컨텐츠를 렌더링하여 반환한다."""


class ScraperApiRenderer(BaseRenderer):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def render(self, url: str) -> str:
        import httpx  # 이미 프로젝트 의존성에 포함됨

        logger.info("Using ScraperAPI for %s", url)
        try:
            params = {
                "api_key": self.api_key,
                "url": url,
                "render": "true",
            }
            response = httpx.get(
                "http://api.scraperapi.com",
                params=params,
                timeout=SCRAPERAPI_TIMEOUT,
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            # API 키가 URL에 포함되므로, 로그에 원본 URL 대신 대상 URL만 출력
            error_msg = f"ScraperAPI failed for {url}: {type(exc).__name__}"
            logger.error(error_msg)
            raise RenderingError(error_msg) from exc


class PlaywrightRenderer(BaseRenderer):
    def _using_external_chrome(self) -> dict:
        chrome_path = os.getenv(CHROME_PATH_ENV)
        base_args = [
            f"--user-agent={USER_AGENT}",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-crashpad",
            "--disable-breakpad",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
        ]

        is_headless = True

        if chrome_path and Path(chrome_path).exists():
            return {
                "headless": is_headless,
                "args": base_args,
                "executable_path": chrome_path,
            }

        return {"headless": is_headless, "args": base_args}

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ko-KR,ko;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def _needs_retry(self, html: str) -> bool:
        if len(html) > 50000:
            return False
        lower = html.lower()
        return any(marker in lower for marker in RETRY_MARKERS)

    def _retry_url(self, url: str, attempt: int) -> str:
        if attempt == 0:
            return url
        suffix = f"_tl_retry={attempt}"
        return f"{url}{'&' if '?' in url else '?'}{suffix}"

    def render(self, url: str) -> str:
        logger.info("Using PlaywrightRenderer for %s", url)
        launch_kwargs = self._using_external_chrome()
        last_html = ""

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(**launch_kwargs)
                try:
                    for attempt in range(MAX_RENDER_ATTEMPTS):
                        target_url = self._retry_url(url, attempt)

                        context = browser.new_context(
                            user_agent=USER_AGENT,
                            device_scale_factor=1.0,
                            is_mobile=False,
                            has_touch=False,
                            locale="en-US",
                            extra_http_headers=self._default_headers(),
                        )
                        try:
                            page = context.new_page()

                            page.goto(
                                target_url,
                                wait_until="domcontentloaded",
                                timeout=30_000,
                            )
                            page.wait_for_selector("body", timeout=30_000)
                            page.wait_for_timeout(500)

                            html = page.content()
                            last_html = html

                            if not self._needs_retry(html):
                                return html

                            wait_seconds = max(MIN_RETRY_WAIT_SECONDS, attempt * 60)
                            logger.info(
                                "retrying %s in %d seconds (attempt %d/%d)",
                                target_url,
                                wait_seconds,
                                attempt + 1,
                                MAX_RENDER_ATTEMPTS,
                            )
                            time.sleep(wait_seconds)
                        finally:
                            context.close()
                finally:
                    browser.close()

        except Exception as exc:
            error_msg = f"failed to render HTML via Chrome for {url}: {exc}"
            logger.error(error_msg)
            raise RenderingError(error_msg) from exc

        return last_html


def get_renderer(config: AppConfig) -> BaseRenderer:
    """AppConfig 설정에 따라 적절한 Renderer 인스턴스를 반환한다."""

    if config.renderer_strategy == "scraperapi":
        if not config.scraperapi_key:
            logger.warning(
                "RENDERER_STRATEGY is scraperapi but SCRAPERAPI_KEY is missing. "
                "Falling back to playwright.",
            )
            return PlaywrightRenderer()
        return ScraperApiRenderer(config.scraperapi_key)

    return PlaywrightRenderer()
