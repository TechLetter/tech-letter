"""블로그 아이콘 고르기와 변환."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from techletter.content.icons import is_webp
from techletter.summary.icons import icon_candidates, to_icon_webp


def png(size: int) -> bytes:
    out = BytesIO()
    Image.new("RGBA", (size, size), (255, 0, 0, 255)).save(out, format="PNG")
    return out.getvalue()


def test_candidates_prefer_apple_touch_then_the_largest_icon() -> None:
    html = """
    <link rel="icon" href="/fav-16.png" sizes="16x16">
    <link rel="icon" href="/fav-32.png" sizes="32x32">
    <link rel="mask-icon" href="/mask.svg">
    <link rel="icon" href="/logo.svg">
    <link rel="apple-touch-icon" href="/apple.png" sizes="180x180">
    """

    assert icon_candidates(html, "https://blog.test/posts/") == [
        "https://blog.test/apple.png",
        "https://blog.test/fav-32.png",
        "https://blog.test/fav-16.png",
        "https://blog.test/favicon.ico",
    ]


def test_an_icon_becomes_a_64px_webp() -> None:
    icon = to_icon_webp(png(180))

    assert icon is not None and is_webp(icon)
    with Image.open(BytesIO(icon)) as image:
        assert image.size == (64, 64)


def test_tiny_or_broken_images_are_rejected() -> None:
    assert to_icon_webp(png(8)) is None
    assert to_icon_webp(b"<html>not an image</html>") is None
