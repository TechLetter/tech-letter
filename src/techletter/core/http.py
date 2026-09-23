"""공유 HTTP 클라이언트.

TLS 검증을 끈 클라이언트는 **따로** 둔다. 인증서가 깨진 블로그 몇 개 때문에
전체 수집의 검증을 끄는 일이 없도록.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from types import TracebackType

__all__ = ["HttpClients", "default_headers"]

logger = get_logger(__name__)

# 봇 차단을 우회하려는 브라우저 위장 헤더. 이걸 빼면 일부 블로그가 403을 준다.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/142.0.0.0 Safari/537.36"
)


def default_headers() -> dict[str, str]:
    return {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }


class HttpClients:
    """프로세스가 공유하는 httpx 클라이언트. 처음 요청될 때 만든다."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        max_connections: int = 20,
    ) -> None:
        self._timeout = timeout
        self._headers = headers if headers is not None else default_headers()
        self._limits = httpx.Limits(
            max_connections=max_connections, max_keepalive_connections=max_connections // 2
        )
        self._client: httpx.AsyncClient | None = None

    def get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers=self._headers,
                limits=self._limits,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None

    async def __aenter__(self) -> HttpClients:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
