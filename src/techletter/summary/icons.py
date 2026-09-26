"""블로그 아이콘 수집. 요약 워커가 `blog.icon_requested` 잡으로 돈다.

사이트의 `apple-touch-icon`(보통 180px) → `<link rel="icon">`(큰 것부터) → `/favicon.ico`
→ RSS 채널 이미지 순으로 시도하고, 처음 열리는 것을 64px webp로 바꿔 저장한다.
Medium 계열처럼 서버 IP가 막힌 사이트는 피드 채널 이미지로 얻는다.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from techletter.core.http import BROWSER_USER_AGENT
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    import httpx

    from techletter.content.icons import BlogIconRepository
    from techletter.content.repositories import BlogRepository
    from techletter.core.jobs.models import Job

__all__ = ["BlogIconHandler", "icon_candidates", "to_icon_webp"]

logger = get_logger(__name__)

ICON_SIZE = 64
MAX_DOWNLOAD_BYTES = 1024 * 1024
MIN_SOURCE_SIZE = 16
TIMEOUT = 10.0
_HEADERS = {"User-Agent": BROWSER_USER_AGENT}


def icon_candidates(html: str, page_url: str) -> list[str]:
    """페이지가 알려 주는 아이콘 주소. 큰 것부터, 마지막에 `/favicon.ico`."""
    from bs4 import BeautifulSoup  # noqa: PLC0415

    soup = BeautifulSoup(html or "", "html.parser")
    ranked: list[tuple[int, int, str]] = []
    for link in soup.find_all("link", href=True):
        rels = {r.lower() for r in (link.get("rel") or [])}
        href = str(link["href"]).strip()
        if not href or href.lower().endswith(".svg") or "mask-icon" in rels:
            continue
        if rels & {"apple-touch-icon", "apple-touch-icon-precomposed"}:
            kind = 0
        elif "icon" in rels:
            kind = 1
        else:
            continue
        ranked.append((kind, -_largest_size(link.get("sizes")), urljoin(page_url, href)))
    ranked.sort()
    urls = [url for _, _, url in ranked]
    urls.append(urljoin(page_url, "/favicon.ico"))
    return list(dict.fromkeys(urls))


def _largest_size(sizes: Any) -> int:
    found = [int(n) for n in re.findall(r"(\d+)x\d+", str(sizes or ""))]
    return max(found) if found else 0


def to_icon_webp(data: bytes) -> bytes | None:
    """정사각 64px webp. 너무 작거나 열리지 않으면 None."""
    from PIL import Image  # noqa: PLC0415

    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            if min(image.size) < MIN_SOURCE_SIZE:
                return None
            rgba = image.convert("RGBA")
    except Exception:
        return None
    rgba.thumbnail((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    canvas.paste(rgba, ((ICON_SIZE - rgba.width) // 2, (ICON_SIZE - rgba.height) // 2))
    out = BytesIO()
    canvas.save(out, format="WEBP", quality=90, method=6)
    return out.getvalue()


class BlogIconHandler:
    def __init__(
        self, blogs: BlogRepository, icons: BlogIconRepository, http: httpx.AsyncClient
    ) -> None:
        self._blogs = blogs
        self._icons = icons
        self._http = http

    async def __call__(self, job: Job) -> None:
        blog_id = str(job.payload.get("blog_id") or job.key)
        blog = await self._blogs.get(blog_id)
        if blog is None or await self._icons.is_manual(blog_id):
            return
        for url in await self._candidates(blog.url, blog.rss_url):
            data = await self._download(url)
            icon = to_icon_webp(data) if data else None
            if icon:
                await self._icons.save(blog_id, icon, source=url, manual=False)
                logger.info("blog icon saved", extra={"blog": blog.name, "source": url})
                return
        await self._icons.mark_missing(blog_id)
        logger.info("blog icon not found", extra={"blog": blog.name})

    async def _candidates(self, site_url: str, rss_url: str) -> list[str]:
        urls: list[str] = []
        html = await self._text(site_url)
        if html is not None:
            urls.extend(icon_candidates(html, site_url))
        feed_image = await self._feed_image(rss_url)
        if feed_image:
            urls.append(feed_image)
        return list(dict.fromkeys(urls))

    async def _feed_image(self, rss_url: str) -> str | None:
        import feedparser  # noqa: PLC0415

        text = await self._text(rss_url)
        if text is None:
            return None
        feed: Any = feedparser.parse(text).feed
        image: Any = feed.get("image") or {}
        href = image.get("href") or image.get("url")
        return str(href) if href else None

    async def _text(self, url: str) -> str | None:
        try:
            response = await self._http.get(
                url, headers=_HEADERS, timeout=TIMEOUT, follow_redirects=True
            )
        except Exception:
            return None
        return response.text if response.status_code == 200 else None

    async def _download(self, url: str) -> bytes | None:
        try:
            response = await self._http.get(
                url, headers=_HEADERS, timeout=TIMEOUT, follow_redirects=True
            )
        except Exception:
            return None
        if response.status_code != 200 or len(response.content) > MAX_DOWNLOAD_BYTES:
            return None
        return response.content
