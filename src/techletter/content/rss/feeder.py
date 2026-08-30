"""RSS 피드 조회·파싱.

파싱(`parse_feed`)과 조회(`RssFeeder`)를 나눴다. 파싱은 순수 함수라
네트워크 없이 픽스처 파일만으로 테스트할 수 있다.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import feedparser

from techletter.core.errors import PermanentError, RetryableError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from time import struct_time

    from techletter.core.http import HttpClients

__all__ = ["FeedItem", "RssFeeder", "parse_feed"]

logger = get_logger(__name__)

# XML이 허용하지 않는 제어 문자. 이게 섞여 있으면 feedparser가 통째로 실패한다.
_INVALID_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
# 재시도해도 소용없는 상태 코드. 나머지(5xx, 429)는 재시도한다.
_PERMANENT_STATUS = frozenset({400, 401, 403, 404, 410, 451})


@dataclass(frozen=True, slots=True)
class FeedItem:
    title: str
    link: str
    published_at: datetime | None


def _to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    # feedparser의 *_parsed는 항상 UTC 기준 struct_time이다.
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


def parse_feed(text: str, *, source: str = "", limit: int = 0) -> list[FeedItem]:
    """RSS/Atom 본문을 항목 목록으로 바꾼다.

    `bozo`는 대부분 "조금 어긋났지만 읽을 수 있음"이다. 여기서는 **항목을
    하나도 못 얻었을 때만** 경고한다.
    """
    parsed: Any = feedparser.parse(_INVALID_CONTROL_CHARS.sub("", text))
    items: list[FeedItem] = []
    for entry in parsed.entries:
        link = (getattr(entry, "link", "") or "").strip()
        if not link:
            continue
        items.append(
            FeedItem(
                title=(getattr(entry, "title", "") or "").strip(),
                link=link,
                published_at=_to_datetime(
                    getattr(entry, "published_parsed", None)
                    or getattr(entry, "updated_parsed", None)
                ),
            )
        )

    if parsed.bozo and not items:
        logger.warning(
            "rss parse produced no items",
            extra={"source": source, "reason": str(parsed.bozo_exception)[:200]},
        )
    elif parsed.bozo:
        logger.debug("rss malformed but usable", extra={"source": source})

    return items[:limit] if limit > 0 else items


class RssFeeder:
    def __init__(self, clients: HttpClients) -> None:
        self._clients = clients

    async def fetch(
        self, rss_url: str, *, limit: int = 0, tls_insecure: bool = False
    ) -> list[FeedItem]:
        import httpx  # noqa: PLC0415

        client = self._clients.get(verify=not tls_insecure)
        try:
            response = await client.get(rss_url)
        except httpx.RequestError as exc:
            raise RetryableError(f"rss fetch failed: {type(exc).__name__}: {exc}") from exc

        if response.status_code != 200:
            # 응답 본문은 로그에도 DB에도 넣지 않는다.
            message = f"rss fetch failed: HTTP {response.status_code}"
            if response.status_code in _PERMANENT_STATUS:
                raise PermanentError(message, reason=f"http_{response.status_code}")
            raise RetryableError(message)

        return parse_feed(response.text, source=rss_url, limit=limit)
