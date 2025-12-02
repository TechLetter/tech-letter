from __future__ import annotations

import logging
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT = 30.0  # seconds
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
CHROME_PATH_ENV = "CHROME_PATH"
MAX_RENDER_ATTEMPTS = 10
MEDIUM_500_MARKER = "Apologies, but something went wrong on our end."
CLOUDFLARE_JS_CHALLENGE_MARKER = "Enable JavaScript and cookies to continue"
CLOUDFLARE_JUST_A_MOMENT_MARKER = "Just a moment"


def _get_chrome_launch_kwargs() -> dict:
    """Go renderer.RenderHTML와 유사하게 Chrome 실행 옵션을 구성한다.

    - CHROME_PATH 환경변수가 설정되어 있고 경로가 존재하면 해당 바이너리를 사용한다.
    - 그렇지 않으면 Playwright 기본 chromium 바이너리를 사용한다.
    """

    chrome_path = os.getenv(CHROME_PATH_ENV)
    kwargs: dict = {
        "headless": True,
        "args": [
            f"--user-agent={USER_AGENT}",
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

    # CHROME_PATH 로 지정된 경로가 실제로 존재하는지 확인한다.
    # 로컬(macOS 등)에서는 없을 수 있으므로 존재하는 경우에만 executable_path 로 사용한다.
    if chrome_path and Path(chrome_path).exists():
        kwargs["executable_path"] = chrome_path

    return kwargs


def _get_default_headers() -> dict[str, str]:
    """브라우저에서 발생한 일반적인 HTML 페이지 요청에 가까운 헤더를 구성한다."""

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


def _is_retryable_error_html(html: str) -> bool:
    """HTML 내용이 일시적인 에러/봇 차단 페이지로 보이는지 판단한다."""

    lower = html.lower()
    if MEDIUM_500_MARKER.lower() in lower:
        return True
    if CLOUDFLARE_JS_CHALLENGE_MARKER.lower() in lower:
        return True
    if CLOUDFLARE_JUST_A_MOMENT_MARKER.lower() in lower:
        return True
    return False


def _build_retry_url(base_url: str, attempt: int) -> str:
    """재시도 횟수에 따라 쿼리 파라미터를 살짝 변경해 캐시된 에러 페이지를 우회한다."""

    if attempt == 0:
        return base_url

    suffix = f"_tl_retry={attempt}"
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{suffix}"


def render_html(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    """지정된 URL을 실제 브라우저(Headless Chrome)로 렌더링한 HTML을 반환한다.

    Go의 renderer.RenderHTML와 마찬가지로:
    - CHROME_PATH 환경변수로 지정된 Chrome/Chromium 바이너리를 우선 사용한다.
    - body가 로드될 때까지 기다린 뒤, 추가로 짧게 대기한 후 전체 HTML을 가져온다.
    네트워크/렌더링 오류 시 예외를 발생시켜 상위 레이어가 재시도/ DLQ 로 처리하도록 한다.
    """

    launch_kwargs = _get_chrome_launch_kwargs()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            try:
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                    device_scale_factor=1.0,
                    is_mobile=False,
                    has_touch=False,
                    locale="en-US",
                    extra_http_headers=_get_default_headers(),
                )
                page = context.new_page()

                html = ""
                for attempt in range(MAX_RENDER_ATTEMPTS):
                    attempt_url = _build_retry_url(url, attempt)

                    # 페이지 이동 및 로드 완료까지 대기 (timeout 단위를 ms로 변환)
                    page.goto(
                        attempt_url, wait_until="load", timeout=int(timeout * 1000)
                    )

                    # body가 준비될 때까지 대기
                    page.wait_for_selector("body", timeout=int(timeout * 1000))

                    # JS로 추가 컨텐츠가 로드될 시간을 약간 더 준다
                    page.wait_for_timeout(1000)

                    html = page.content()
                    if not _is_retryable_error_html(html):
                        return html

                    logger.warning(
                        "temporary HTML detected for %s (attempt %d/%d)",
                        attempt_url,
                        attempt + 1,
                        MAX_RENDER_ATTEMPTS,
                    )

                    if attempt < MAX_RENDER_ATTEMPTS - 1:
                        # 에러 페이지가 계속 나오는 경우 잠시 대기 후 재시도한다.
                        page.wait_for_timeout(1000 * (attempt + 1))

            finally:
                browser.close()

            # 모든 재시도에서도 에러 페이지만 받은 경우 마지막 HTML을 반환한다.
            return html
    except Exception as exc:  # noqa: BLE001
        logger.error("failed to render HTML via headless Chrome for %s: %s", url, exc)
        raise
