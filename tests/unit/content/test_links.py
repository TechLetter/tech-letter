"""게시물 링크 정규화 규칙."""

from __future__ import annotations

import pytest

from techletter.content.links import link_slug, normalize_link


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com/article/", "https://example.com/article"),
        ("HTTPS://EXAMPLE.COM/article", "https://example.com/article"),
        (
            "https://example.com/article?utm_source=rss&utm_campaign=weekly",
            "https://example.com/article",
        ),
        ("https://example.com/article?fbclid=abc&ref=home", "https://example.com/article?ref=home"),
        ("https://example.com/article?b=2&a=1", "https://example.com/article?a=1&b=2"),
        ("https://example.com/article#comments", "https://example.com/article"),
        ("https://example.com:443/article", "https://example.com/article"),
        ("http://example.com:80/article", "http://example.com/article"),
        ("https://example.com:8443/article", "https://example.com:8443/article"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/", "https://example.com/"),
        ("https://www.example.com/article/", "https://www.example.com/article"),
        ("", ""),
        ("   ", ""),
        ("not-a-url", "not-a-url"),
        ("http://[invalid", "http://[invalid"),
    ],
)
def test_normalize_link_table(raw: str, expected: str) -> None:
    assert normalize_link(raw) == expected


def test_all_known_tracking_parameters_are_removed() -> None:
    tracking = (
        "fbclid=x&gclid=x&dclid=x&igshid=x&mc_cid=x&mc_eid=x&"
        "_ga=x&_gl=x&ref_src=x&yclid=x&utm_medium=email"
    )

    assert (
        normalize_link(f"https://example.com/article?{tracking}") == "https://example.com/article"
    )


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://tech.socarcorp.kr/fe/2026/02/24/frame2-web.html", "frame2-web"),
        ("https://tech.socar.kr/fe/2026/02/25/frame2-web", "frame2-web"),
        ("https://insight.infograb.net/blog/2025/09/24/gitlab-dedicated/", "gitlab-dedicated"),
        ("https://www.uber.com/us/en/blog/Taming-ML/", "taming-ml"),
        ("https://alpha.test/", ""),
        ("https://alpha.test/?p=123", ""),
    ],
)
def test_the_slug_ignores_extension_trailing_slash_and_case(url: str, slug: str) -> None:
    assert link_slug(url) == slug
