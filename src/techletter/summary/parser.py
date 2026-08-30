"""HTML에서 본문과 썸네일을 뽑는다.

`<img>` 후보 다운로드에는 개수 제한(`MAX_IMAGE_CANDIDATES`)과 픽셀 상한
(`Image.MAX_IMAGE_PIXELS`)을 둔다 — 제한이 없으면 이미지가 수백 개인
페이지에서 요약 하나가 몇 분씩 걸리고 decompression bomb에도 노출된다.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from techletter.core.errors import PermanentError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    import httpx

__all__ = ["MAX_IMAGE_CANDIDATES", "extract_plain_text", "extract_thumbnail"]

logger = get_logger(__name__)

MIN_THUMBNAIL_SIZE = 300
MAX_IMAGE_CANDIDATES = 10
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# 디코딩 폭탄 방어. 8000x8000 정도면 어떤 썸네일에도 충분하다.
MAX_IMAGE_PIXELS = 64_000_000
IMAGE_TIMEOUT = 10.0

_META_PROPERTIES = ("og:image", "og:image:url", "og:image:secure_url")
_META_NAMES = ("twitter:image", "twitter:image:src", "thumbnail", "image")


def extract_plain_text(html: str) -> str:
    import trafilatura  # noqa: PLC0415

    text = trafilatura.extract(html, include_comments=False, output_format="txt")
    if not text or not text.strip():
        raise PermanentError("failed to extract main text", reason="extraction_failed")
    return text.strip()


def _absolute(url: Any, page_url: str | None) -> str:
    if not isinstance(url, str) or not url:
        return ""
    if url.startswith(("data:", "about:", "javascript:")):
        return ""
    return urljoin(page_url, url) if page_url else url


def _int_attr(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


async def _image_size(client: httpx.AsyncClient, url: str) -> tuple[int, int] | None:
    """이미지를 내려받아 실제 크기를 잰다. 실패하면 None(다음 후보로)."""
    from PIL import Image  # noqa: PLC0415

    # Pillow의 기본 상한은 넉넉해서 그대로 두면 폭탄을 그대로 연다.
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        response = await client.get(url, timeout=IMAGE_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        declared = response.headers.get("Content-Length")
        if declared and _int_attr(declared) and int(declared) > MAX_IMAGE_BYTES:
            return None
        data = response.content[:MAX_IMAGE_BYTES]
        with Image.open(BytesIO(data)) as image:
            return int(image.size[0]), int(image.size[1])
    except Exception:
        return None


def _meta_thumbnail(soup: Any, page_url: str | None) -> str:
    tag = soup.find("meta", attrs={"property": list(_META_PROPERTIES)})
    if tag and tag.get("content"):
        return _absolute(tag["content"], page_url)
    for name in _META_NAMES:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return _absolute(tag["content"], page_url)
    tag = soup.find("meta", attrs={"itemprop": "image"})
    return _absolute(tag["content"], page_url) if tag and tag.get("content") else ""


def _link_thumbnail(soup: Any, page_url: str | None) -> str:
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        href = link.get("href") or ""
        if href and ("image_src" in rel or "thumbnail" in rel):
            return _absolute(href, page_url)
    return ""


async def _img_thumbnail(soup: Any, page_url: str | None, client: httpx.AsyncClient | None) -> str:
    """`<img>` 중에서 충분히 큰 것을 고른다.

    속성에 크기가 적혀 있으면 그것만으로 판단하고, 없을 때만 내려받는다.
    내려받는 후보는 `MAX_IMAGE_CANDIDATES`개까지다.
    """
    fetched = 0
    fallback = ""
    for img in soup.find_all("img"):
        url = _absolute(img.get("src"), page_url)
        if not url:
            continue
        fallback = fallback or url

        width, height = _int_attr(img.get("width")), _int_attr(img.get("height"))
        if (width is not None and width < MIN_THUMBNAIL_SIZE) or (
            height is not None and height < MIN_THUMBNAIL_SIZE
        ):
            continue
        if width is not None and height is not None:
            return url

        if client is None or fetched >= MAX_IMAGE_CANDIDATES:
            continue
        fetched += 1
        size = await _image_size(client, url)
        if size and size[0] >= MIN_THUMBNAIL_SIZE and size[1] >= MIN_THUMBNAIL_SIZE:
            return url

    return fallback


async def extract_thumbnail(
    html: str, page_url: str | None = None, client: httpx.AsyncClient | None = None
) -> str:
    """메타 태그 → link → 큰 `<img>` → 첫 `<img>` 순으로 고른다.

    `client`가 없으면 네트워크를 쓰지 않는다(테스트·오프라인 경로).
    """
    from bs4 import BeautifulSoup  # noqa: PLC0415

    soup = BeautifulSoup(html, "html.parser")
    return (
        _meta_thumbnail(soup, page_url)
        or _link_thumbnail(soup, page_url)
        or await _img_thumbnail(soup, page_url, client)
    )
