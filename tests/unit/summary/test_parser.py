"""HTML 추출 — 네트워크 없이 픽스처로만 검증한다."""

from __future__ import annotations

from pathlib import Path

import pytest

from techletter.core.errors import PermanentError
from techletter.summary.parser import (
    MAX_IMAGE_CANDIDATES,
    extract_plain_text,
    extract_thumbnail,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "html"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_the_article_body_is_extracted() -> None:
    text = extract_plain_text(fixture("article.html"))

    assert "리밸런싱" in text
    assert "<p>" not in text


def test_a_page_without_body_text_is_permanent() -> None:
    with pytest.raises(PermanentError) as excinfo:
        extract_plain_text("<html><body></body></html>")

    assert excinfo.value.reason == "extraction_failed"


async def test_the_meta_image_wins_and_is_made_absolute() -> None:
    url = await extract_thumbnail(fixture("article.html"), "https://blog.test/posts/1")

    assert url == "https://blog.test/images/cover.png"


async def test_a_large_img_is_chosen_from_its_attributes() -> None:
    """속성에 크기가 있으면 내려받지 않는다."""
    url = await extract_thumbnail(fixture("no-meta-image.html"), "https://blog.test/p")

    assert url == "https://blog.test/images/big.png"


async def test_data_uris_are_skipped() -> None:
    html = (
        "<html><body>"
        '<img src="data:image/png;base64,AAA">'
        '<img src="/ok.png" width="400" height="400">'
        "</body></html>"
    )

    assert await extract_thumbnail(html, "https://blog.test/p") == "https://blog.test/ok.png"


async def test_no_images_yields_an_empty_string() -> None:
    assert await extract_thumbnail("<html><body><p>글</p></body></html>") == ""


async def test_without_a_client_no_image_is_downloaded() -> None:
    """네트워크를 못 쓰면 속성만으로 판단하고 첫 이미지로 떨어진다."""
    html = '<html><body><img src="/unknown-size.png"></body></html>'

    assert (
        await extract_thumbnail(html, "https://blog.test/p") == "https://blog.test/unknown-size.png"
    )


async def test_image_downloads_are_capped() -> None:
    """후보 개수 제한이 없으면 이미지가 많은 페이지에서 몇 분씩 걸린다."""
    import httpx

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(404)

    imgs = "".join(f'<img src="/img{i}.png">' for i in range(50))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client:
        await extract_thumbnail(f"<html><body>{imgs}</body></html>", "https://b.test/p", client)

    assert len(requested) == MAX_IMAGE_CANDIDATES
