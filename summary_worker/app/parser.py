from __future__ import annotations

from io import BytesIO
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from PIL import Image
import trafilatura


MIN_THUMBNAIL_WIDTH = 300
MIN_THUMBNAIL_HEIGHT = 300
IMAGE_REQUEST_TIMEOUT = 10.0
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def extract_plain_text(html: str) -> str:
    """HTML에서 본문 텍스트를 추출한다.

    Go ParseHtmlWithReadability/ParseHtmlWithTrafilatura 와 유사하게
    trafilatura를 사용해 메인 콘텐츠를 뽑아낸다.
    """
    text = trafilatura.extract(html, include_comments=False, output_format="txt")
    if not text:
        raise ValueError("failed to extract main text from HTML")
    return text.strip()


def _make_absolute_url(url: object, page_url: str | None) -> str:
    """bs4 AttributeValue를 포함해 어떤 값이 와도 안전하게 문자열 URL을 만든다."""
    if not isinstance(url, str) or not url:
        return ""
    if not page_url:
        return url
    return urljoin(page_url, url)


def _parse_int_from_attribute(value: object | None) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fetch_image_dimensions(image_url: str) -> tuple[int | None, int | None]:
    """이미지를 네트워크로 가져와 실제 픽셀 크기를 반환한다.

    실패하면 (None, None)을 반환하여 호출 측에서 다른 후보를 시도할 수 있도록 한다.
    """
    try:
        resp = httpx.get(
            image_url,
            timeout=IMAGE_REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()

        content_length = resp.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_IMAGE_BYTES:
                    return None, None
            except (TypeError, ValueError):
                # 잘못된 Content-Length는 무시하고 계속 진행한다.
                pass

        data = resp.content
        if len(data) > MAX_IMAGE_BYTES:
            data = data[:MAX_IMAGE_BYTES]

        with Image.open(BytesIO(data)) as img:
            width, height = img.size
            return int(width), int(height)
    except Exception:
        # 네트워크 오류, 디코딩 실패 등은 호출 쪽에서 다른 후보를 시도할 수 있도록 조용히 무시한다.
        return None, None


def _extract_meta_thumbnail(soup: BeautifulSoup, page_url: str | None) -> str:
    og_image = soup.find(
        "meta",
        attrs={
            "property": [
                "og:image",
                "og:image:url",
                "og:image:secure_url",
            ]
        },
    )
    if og_image and og_image.get("content"):
        return _make_absolute_url(og_image["content"], page_url)

    for name in ["twitter:image", "twitter:image:src", "thumbnail", "image"]:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return _make_absolute_url(tag["content"], page_url)

    itemprop = soup.find("meta", attrs={"itemprop": "image"})
    if itemprop and itemprop.get("content"):
        return _make_absolute_url(itemprop["content"], page_url)

    return ""


def _extract_link_thumbnail(soup: BeautifulSoup, page_url: str | None) -> str:
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        rel_joined = " ".join(rel).lower()
        href = link.get("href") or ""
        if href and ("image_src" in rel_joined or "thumbnail" in rel_joined):
            return _make_absolute_url(href, page_url)

    return ""


def _extract_img_thumbnail(soup: BeautifulSoup, page_url: str | None) -> str:
    for img in soup.find_all("img"):
        src_attr = img.get("src")
        if not isinstance(src_attr, str) or not src_attr:
            continue

        src = src_attr

        # data URI, about: 등은 무시
        if src.startswith("data:") or src.startswith("about:"):
            continue

        abs_src = _make_absolute_url(src, page_url)
        if not abs_src:
            continue

        width = _parse_int_from_attribute(img.get("width"))
        height = _parse_int_from_attribute(img.get("height"))

        # Go 구현과 동일하게, 명시된 width/height가 너무 작은 경우는 바로 배제한다.
        if width is not None and width < MIN_THUMBNAIL_WIDTH:
            continue
        if height is not None and height < MIN_THUMBNAIL_HEIGHT:
            continue

        # 명시된 크기만으로도 충분히 큰 경우 바로 선택.
        if (
            width is not None
            and height is not None
            and width >= MIN_THUMBNAIL_WIDTH
            and height >= MIN_THUMBNAIL_HEIGHT
        ):
            return abs_src

        # 나머지 경우에는 실제 이미지를 내려받아 크기를 확인한다.
        real_width, real_height = _fetch_image_dimensions(abs_src)
        if (
            real_width is not None
            and real_height is not None
            and real_width >= MIN_THUMBNAIL_WIDTH
            and real_height >= MIN_THUMBNAIL_HEIGHT
        ):
            return abs_src

    return ""


def extract_thumbnail(html: str, page_url: str | None = None) -> str:
    """썸네일 이미지를 추출한다.

    우선순위:
    - og:image, twitter:image, itemprop=image
    - <link rel="image_src"|"*thumbnail*">
    - 크기가 충분히 큰 <img> (width/height 또는 실제 이미지 크기 기준)
    - 최후에는 첫 번째 <img> src
    """
    soup = BeautifulSoup(html, "html.parser")

    thumbnail = _extract_meta_thumbnail(soup, page_url)
    if thumbnail:
        return thumbnail

    thumbnail = _extract_link_thumbnail(soup, page_url)
    if thumbnail:
        return thumbnail

    thumbnail = _extract_img_thumbnail(soup, page_url)
    if thumbnail:
        return thumbnail

    # 마지막 fallback: 첫 번째 <img>
    img = soup.find("img")
    if img and img.get("src"):
        return _make_absolute_url(img["src"], page_url)

    return ""
