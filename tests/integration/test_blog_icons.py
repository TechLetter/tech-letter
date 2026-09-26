"""블로그 아이콘 수집 잡 — 실제 Mongo에 저장한다."""

from __future__ import annotations

from io import BytesIO

import httpx
import pytest
from PIL import Image

from techletter.content.icons import BlogIconRepository, is_webp
from techletter.content.models import Blog
from techletter.content.repositories import BlogRepository
from techletter.core.jobs.models import Job
from techletter.core.jobs.types import JobType
from techletter.summary.icons import BlogIconHandler

pytestmark = pytest.mark.integration


def png(size: int) -> bytes:
    out = BytesIO()
    Image.new("RGBA", (size, size), (0, 0, 255, 255)).save(out, format="PNG")
    return out.getvalue()


def client(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: routes.get(str(r.url), httpx.Response(404)))
    )


async def run(
    mongo_db, routes: dict[str, httpx.Response], rasterize_svg=None
) -> tuple[str, BlogIconRepository]:
    blogs = BlogRepository(mongo_db)
    blog = await blogs.insert(
        Blog(name="Alpha", url="https://alpha.test/", rss_url="https://alpha.test/feed/")
    )
    icons = BlogIconRepository(mongo_db)
    handler = BlogIconHandler(blogs, icons, client(routes), rasterize_svg)
    await handler(
        Job(type=JobType.BLOG_ICON_REQUESTED, key=str(blog.id), payload={"blog_id": str(blog.id)})
    )
    return str(blog.id), icons


async def test_the_site_icon_is_saved_as_webp(mongo_db) -> None:
    blog_id, icons = await run(
        mongo_db,
        {
            "https://alpha.test/": httpx.Response(
                200, text='<link rel="apple-touch-icon" href="/apple.png">'
            ),
            "https://alpha.test/apple.png": httpx.Response(200, content=png(180)),
        },
    )

    icon = await icons.get(blog_id)
    assert icon is not None and is_webp(icon["data"])


async def test_a_blocked_site_falls_back_to_the_feed_image(mongo_db) -> None:
    """Medium 계열은 서버 IP에 403을 준다. 피드의 채널 이미지로 얻는다."""
    feed = """<rss><channel><title>A</title><image><url>https://cdn.test/logo.png</url>
    <title>A</title><link>https://alpha.test/</link></image></channel></rss>"""
    blog_id, icons = await run(
        mongo_db,
        {
            "https://alpha.test/": httpx.Response(403),
            "https://alpha.test/feed/": httpx.Response(200, text=feed),
            "https://cdn.test/logo.png": httpx.Response(200, content=png(120)),
        },
    )

    assert await icons.get(blog_id) is not None


async def test_an_svg_only_site_is_rasterized(mongo_db) -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect/></svg>'
    seen: list[bytes] = []

    async def rasterize(data: bytes) -> bytes:
        seen.append(data)
        return png(128)

    blog_id, icons = await run(
        mongo_db,
        {
            "https://alpha.test/": httpx.Response(
                200, text='<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">'
            ),
            "https://alpha.test/assets/favicon.svg": httpx.Response(200, content=svg),
        },
        rasterize,
    )

    assert seen == [svg]
    assert await icons.get(blog_id) is not None


async def test_nothing_found_is_recorded_as_missing(mongo_db) -> None:
    blog_id, icons = await run(mongo_db, {"https://alpha.test/": httpx.Response(200, text="<p/>")})

    assert await icons.get(blog_id) is None
    assert blog_id in await icons.blog_ids_with_record()
