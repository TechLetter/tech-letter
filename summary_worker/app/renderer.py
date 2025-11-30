from __future__ import annotations

import logging
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT = 30.0  # seconds
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
CHROME_PATH_ENV = "CHROME_PATH"


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
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()

                # 페이지 이동 및 로드 완료까지 대기 (timeout 단위를 ms로 변환)
                page.goto(url, wait_until="load", timeout=int(timeout * 1000))

                # body가 준비될 때까지 대기
                page.wait_for_selector("body", timeout=int(timeout * 1000))

                # JS로 추가 컨텐츠가 로드될 시간을 약간 더 준다 (Go에서 Sleep(1s)와 유사)
                page.wait_for_timeout(1000)

                html = page.content()
            finally:
                browser.close()
            return html
    except Exception as exc:  # noqa: BLE001
        logger.error("failed to render HTML via headless Chrome for %s: %s", url, exc)
        raise
