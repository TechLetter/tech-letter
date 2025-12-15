from __future__ import annotations
import logging
import os
from pathlib import Path
import time
from playwright.sync_api import ViewportSize, sync_playwright

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
CHROME_PATH_ENV = "CHROME_PATH"
MAX_RENDER_ATTEMPTS = 20

RETRY_MARKERS = [
    "apologies, but something went wrong on our end.",
    "enable javascript and cookies to continue",
    "just a moment",
    "verifying you are human",
    "challenges.cloudflare.com",
    "needs to review the security of your connection before proceeding",
    "Out of nothing, something.",
]


def _using_external_chrome() -> dict:
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


def _default_headers() -> dict[str, str]:
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


def _needs_retry(html: str) -> bool:
    lower = html.lower()
    return any(marker in lower for marker in RETRY_MARKERS)


def _retry_url(url: str, attempt: int) -> str:
    if attempt == 0:
        return url
    suffix = f"_tl_retry={attempt}"
    return f"{url}{'&' if '?' in url else '?'}{suffix}"


def render_html(url: str) -> str:
    launch_kwargs = _using_external_chrome()
    last_html = ""

    try:
        with sync_playwright() as p:
            for attempt in range(MAX_RENDER_ATTEMPTS):
                target_url = _retry_url(url, attempt)
                browser = p.chromium.launch(**launch_kwargs)

                try:
                    context = browser.new_context(
                        user_agent=USER_AGENT,
                        device_scale_factor=1.0,
                        is_mobile=False,
                        has_touch=False,
                        locale="en-US",
                        extra_http_headers=_default_headers(),
                    )
                    page = context.new_page()

                    page.goto(
                        target_url,
                        wait_until="load",
                        timeout=30_000,
                    )
                    page.wait_for_selector("body", timeout=30_000)
                    page.wait_for_timeout(500)

                    html = page.content()
                    last_html = html

                    if not _needs_retry(html):
                        return html
                    else:
                        wait_seconds = attempt * 60
                        logger.info(
                            "retrying %s in %d seconds", target_url, wait_seconds
                        )
                        time.sleep(wait_seconds)

                finally:
                    browser.close()

    except Exception as exc:
        logger.error("failed to render HTML via Chrome for %s: %s", url, exc)
        raise

    return last_html
