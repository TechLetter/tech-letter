from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from time import struct_time

import httpx
import feedparser


logger = logging.getLogger(__name__)


FEEDER_TIMEOUT_SECONDS = 30.0

# Go rssUserAgent 와 동일한 문자열을 그대로 사용한다.
RSS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/142.0.0.0 Safari/537.36"
)

# XML에서 허용되지 않는 제어 문자 범위와 동일한 정규식 (Go invalidControlCharRegex).
_INVALID_CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


@dataclass(slots=True)
class RssFeedItem:
    title: str
    link: str
    published_at: datetime | None


def _clean_control_characters(text: str) -> str:
    """RSS 응답 본문에서 XML이 허용하지 않는 제어 문자를 제거한다."""

    return _INVALID_CONTROL_CHAR_REGEX.sub("", text)


def _build_client() -> httpx.Client:
    """Go FetchRssFeeds 와 동일한 타임아웃/검증 정책을 가진 HTTP 클라이언트를 생성한다."""

    # verify=False 는 TLS 인증서 검증을 건너뛰므로, RSS 엔드포인트의 설정 문제로 인한 실패를 줄이기 위한 선택이다.
    return httpx.Client(
        timeout=FEEDER_TIMEOUT_SECONDS,
        verify=False,
        follow_redirects=True,
        headers={
            "User-Agent": RSS_USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
        },
    )


def fetch_rss_feeds(rss_url: str, limit: int) -> list[RssFeedItem]:
    """지정한 RSS URL 로부터 피드를 가져와 RssFeedItem 목록으로 반환한다.

    Go `feeder.FetchRssFeeds` 와 동일한 동작을 목표로 한다.
    """

    client = _build_client()

    try:
        resp = client.get(rss_url)
    except httpx.RequestError as exc:  # noqa: BLE001
        raise RuntimeError(f"failed to fetch RSS feed: {exc}") from exc
    finally:
        client.close()

    if resp.status_code != 200:
        body_sample = resp.text[:500]
        raise RuntimeError(
            f"failed to fetch RSS feed: status code {resp.status_code}, "
            f"url: {rss_url}, body: {body_sample}",
        )

    cleaned_text = _clean_control_characters(resp.text)
    parsed = feedparser.parse(cleaned_text)

    if parsed.bozo:
        # feedparser 가 파싱에 실패한 경우 bozo_exception 에 세부 정보가 들어있다.
        logger.warning(
            "feedparser bozo flag set for %s: %s", rss_url, parsed.bozo_exception
        )

    items: list[RssFeedItem] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""

        published_at: datetime | None = None
        # Go 구현처럼 PublishedParsed 우선, 없으면 UpdatedParsed 사용.
        dt_struct = getattr(entry, "published_parsed", None) or getattr(
            entry, "updated_parsed", None
        )
        if dt_struct is not None:
            # dt_struct 는 time.struct_time 이며, UTC 기준으로 해석한다.
            published_at = datetime.fromtimestamp(
                _to_timestamp(dt_struct), tz=timezone.utc
            )

        items.append(RssFeedItem(title=title, link=link, published_at=published_at))

    if limit > 0 and len(items) > limit:
        items = items[:limit]

    return items


def _to_timestamp(value: struct_time) -> float:
    """time.struct_time 을 POSIX 타임스탬프로 변환한다.

    feedparser 는 time.struct_time 을 사용하므로, calendar.timegm 과 동일한 처리를 수행한다.
    여기서는 의존성 최소화를 위해 직접 계산하지 않고 datetime.fromtimestamp 를 사용하므로,
    struct_time 이 datetime 으로 직접 변환 가능한 경우에만 호출된다.
    """

    import calendar

    return float(calendar.timegm(value))
