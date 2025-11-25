from __future__ import annotations

import logging

import pytest

from summary_worker.app.parser import extract_plain_text, extract_thumbnail
from summary_worker.app.renderer import render_html


logger = logging.getLogger(__name__)


TEST_URLS: list[str] = [
    "https://devocean.sk.com/blog/techBoardDetail.do?ID=168047&boardType=techBlog",
    "https://microservices.io//post/architecture/2025/11/23/qconsf-2025-microservices-platforms.html",
    "https://tech.kakao.com/posts/797",
    "https://techblog.lycorp.co.jp/ko/connecting-thousands-of-services-with-central-dogma-control-plane",
    "https://techblog.gccompany.co.kr/%EC%97%AC%EA%B8%B0%EC%96%B4%EB%95%8C-%EA%B2%80%EC%83%89-%EA%B4%91%EA%B3%A0-%EB%9E%AD%ED%82%B9-%EB%B6%80%EC%8A%A4%ED%8C%85-%EA%B5%AC%EC%B6%95%EA%B8%B0-9299053a3c3d?source=rss----18356045d353---4",
]


@pytest.mark.parametrize("url", TEST_URLS)
def test_renderer_and_parser_on_url(url: str) -> None:
    """실제 블로그 URL들에 대해 renderer, parser가 제대로 동작하는지 검증한다.

    - renderer.render_html: 전체 HTML이 정상적으로 렌더링되는지
    - parser.extract_plain_text: 본문 텍스트가 충분히 추출되는지 (길이 > 0)
    - parser.extract_thumbnail: 썸네일 URL이 비어있지 않은지

    외부 네트워크와 실제 사이트에 의존하는 통합 테스트 성격의 유닛 테스트다.
    """

    logging.basicConfig(level=logging.INFO)
    logger.info("[TEST] URL=%s", url)

    # 1. HTML 렌더링
    html = render_html(url)
    assert isinstance(html, str)
    assert len(html) > 0, f"empty html for url={url}"

    # 2. 본문 텍스트 추출
    text = extract_plain_text(html)
    assert isinstance(text, str)
    assert len(text) > 0, f"empty plain text for url={url}"

    # 3. 썸네일 추출
    thumbnail = extract_thumbnail(html, url)
    assert isinstance(thumbnail, str)
    assert thumbnail != "", f"thumbnail should not be empty for url={url}"
