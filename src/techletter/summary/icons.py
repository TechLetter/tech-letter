"""블로그 아이콘 수집. 요약 워커가 `blog.icon_requested` 잡으로 돈다.

사이트의 `apple-touch-icon`(보통 180px) → `<link rel="icon">`(큰 것부터) → `/favicon.ico`
→ SVG 아이콘 → RSS 채널 이미지 순으로 시도하고, 처음 열리는 것을 64px webp로 바꿔 저장한다.
Medium 계열처럼 서버 IP가 막힌 사이트는 피드 채널 이미지로 얻는다. SVG는 Pillow가 못 열어
브라우저로 그린다(하이퍼커넥트·Project Zero는 아이콘이 SVG뿐이다).

Medium 블로그는 페이지 아이콘도 피드 채널 이미지도 Medium 로고라 13곳이 같은 아이콘이 된다.
그 로고는 건너뛴다. 퍼블리케이션 로고는 Medium이 서버 요청을 모두 막아 받을 수 없어서,
어드민이 회사 홈페이지 같은 다른 주소를 주면(`site_url`) 그 사이트 아이콘을 받는다.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from techletter.core.http import BROWSER_USER_AGENT
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    import httpx

    from techletter.content.icons import BlogIconRepository
    from techletter.content.repositories import BlogRepository
    from techletter.core.jobs.models import Job

__all__ = ["BlogIconHandler", "icon_candidates", "is_generic_icon", "is_svg", "to_icon_webp"]

logger = get_logger(__name__)

ICON_SIZE = 64
MAX_DOWNLOAD_BYTES = 1024 * 1024
MIN_SOURCE_SIZE = 16
TIMEOUT = 10.0
# zstd로 주는 사이트(Netflix)는 httpx가 풀다 실패한다(`DecodingError`). gzip만 받는다.
_HEADERS = {"User-Agent": BROWSER_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
# Medium 기본 로고(페이지 apple-touch-icon, 피드 채널 이미지).
_GENERIC_ICON_MARKERS = (
    "10fd5c419ac61637245384e7099e131627900034828f4f386bdaa47a74eae156",
    "1*TGH72Nnw24QL3iV9IOm4VA",
)
_GENERIC_ICON_HOSTS = frozenset({"medium.com"})


def is_generic_icon(url: str) -> bool:
    """블로그가 아니라 호스팅 플랫폼의 아이콘이다."""
    host = (urlparse(url).hostname or "").lower()
    return host in _GENERIC_ICON_HOSTS or any(m in url for m in _GENERIC_ICON_MARKERS)


def icon_candidates(html: str, page_url: str) -> list[str]:
    """페이지가 알려 주는 아이콘 주소. 큰 것부터, 그다음 `/favicon.ico`, 마지막에 SVG."""
    from bs4 import BeautifulSoup  # noqa: PLC0415

    soup = BeautifulSoup(html or "", "html.parser")
    ranked: list[tuple[int, int, str]] = []
    svgs: list[str] = []
    for link in soup.find_all("link", href=True):
        rels = {r.lower() for r in (link.get("rel") or [])}
        href = str(link["href"]).strip()
        # mask-icon은 단색 실루엣이라 아이콘으로 쓰지 않는다.
        if not href or "mask-icon" in rels:
            continue
        if _is_svg_link(href, link.get("type")):
            if "icon" in rels:
                svgs.append(urljoin(page_url, href))
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
    urls.extend(svgs)
    return list(dict.fromkeys(urls))


def _is_svg_link(href: str, type_: Any) -> bool:
    return urlparse(href).path.lower().endswith(".svg") or "svg" in str(type_ or "").lower()


def is_svg(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:2048])


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
        self,
        blogs: BlogRepository,
        icons: BlogIconRepository,
        http: httpx.AsyncClient,
        rasterize_svg: Callable[[bytes], Awaitable[bytes | None]] | None = None,
    ) -> None:
        self._blogs = blogs
        self._icons = icons
        self._http = http
        self._rasterize_svg = rasterize_svg

    async def __call__(self, job: Job) -> None:
        blog_id = str(job.payload.get("blog_id") or job.key)
        site_url = job.payload.get("site_url")
        blog = await self._blogs.get(blog_id)
        if blog is None or await self._icons.is_manual(blog_id):
            return
        if site_url:
            # 어드민이 고른 주소. 직접 올린 아이콘처럼 자동 수집이 덮지 않고,
            # 못 받으면 지금 아이콘을 그대로 둔다.
            urls = await self._candidates(str(site_url), None)
        else:
            urls = await self._candidates(blog.url, blog.rss_url)
        for url in urls:
            icon = await self._fetch_icon(url)
            if icon:
                await self._icons.save(blog_id, icon, source=url, manual=bool(site_url))
                logger.info("blog icon saved", extra={"blog": blog.name, "source": url})
                return
        if not site_url:
            await self._icons.mark_missing(blog_id)
        logger.info("blog icon not found", extra={"blog": blog.name, "site_url": site_url})

    async def _fetch_icon(self, url: str) -> bytes | None:
        data = await self._download(url)
        if data and is_svg(data):
            data = await self._rasterize_svg(data) if self._rasterize_svg else None
        return to_icon_webp(data) if data else None

    async def _candidates(self, site_url: str, rss_url: str | None) -> list[str]:
        urls: list[str] = []
        html = await self._text(site_url)
        if html is not None:
            urls.extend(icon_candidates(html, site_url))
        feed_image = await self._feed_image(rss_url) if rss_url else None
        if feed_image:
            urls.append(feed_image)
        return [url for url in dict.fromkeys(urls) if not is_generic_icon(url)]

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
