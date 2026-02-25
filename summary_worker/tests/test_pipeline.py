import logging

import pytest

from summary_worker.app.parser import extract_plain_text, extract_thumbnail
from summary_worker.app.renderer import PlaywrightRenderer
from summary_worker.app.validator import validate_plain_text
from summary_worker.app.exceptions import ValidationError


logger = logging.getLogger(__name__)

_renderer = PlaywrightRenderer()

TEST_URLS: list[str] = [
    "https://devocean.sk.com/blog/techBoardDetail.do?ID=168047&boardType=techBlog",
    "https://microservices.io//post/architecture/2025/11/23/qconsf-2025-microservices-platforms.html",
    "https://tech.kakao.com/posts/797",
    "https://techblog.lycorp.co.jp/ko/connecting-thousands-of-services-with-central-dogma-control-plane",
    "https://techblog.gccompany.co.kr/%EC%97%AC%EA%B8%B0%EC%96%B4%EB%95%8C-%EA%B2%80%EC%83%89-%EA%B4%91%EA%B3%A0-%EB%9E%AD%ED%82%B9-%EB%B6%80%EC%8A%A4%ED%8C%85-%EA%B5%AC%EC%B6%95%EA%B8%B0-9299053a3c3d?source=rss----18356045d353---4",
]


@pytest.mark.parametrize("url", TEST_URLS)
def test_render_parse_validate_pipeline(url: str) -> None:
    """실제 블로그 URL들에 대해 renderer, parser가 제대로 동작하는지 검증한다.

    - renderer.render: 전체 HTML이 정상적으로 렌더링되는지
    - parser.extract_plain_text: 본문 텍스트가 충분히 추출되는지 (길이 > 0)
    - parser.extract_thumbnail: 썸네일 URL이 비어있지 않은지

    외부 네트워크와 실제 사이트에 의존하는 통합 테스트 성격의 유닛 테스트다.
    """

    logging.basicConfig(level=logging.INFO)
    logger.info("[TEST] URL=%s", url)

    # 1. HTML 렌더링
    html = _renderer.render(url)
    assert isinstance(html, str)
    assert len(html) > 0, f"empty html for url={url}"

    # 2. 본문 텍스트 추출
    text = extract_plain_text(html)
    assert isinstance(text, str)
    assert len(text) > 0, f"empty plain text for url={url}"

    # 3. 본문 텍스트 검증
    validate_plain_text(text)

    # 4. 썸네일 추출
    thumbnail = extract_thumbnail(html, url)
    assert isinstance(thumbnail, str)
    assert thumbnail != "", f"thumbnail should not be empty for url={url}"


def test_validate_not_found_error_pipeline():
    html = '<!DOCTYPE html><html lang="en"><head>\n  <meta charset="utf-8">\n  <meta http-equiv="X-UA-Compatible" content="IE=edge">\n  <meta name="viewport" content="width=device-width, initial-scale=1"><!-- Begin Jekyll SEO tag v2.6.0 -->\n<title>컬리 기술 블로그</title>\n<meta name="generator" content="Jekyll v3.8.5">\n<meta property="og:title" content="컬리 기술 블로그">\n<meta property="og:locale" content="en_US">\n<meta name="description" content="컬리 기술 블로그">\n<meta property="og:description" content="컬리 기술 블로그">\n<link rel="canonical" href="http://thefarmersfront.github.io/404.html">\n<meta property="og:url" content="http://thefarmersfront.github.io/404.html">\n<meta property="og:site_name" content="컬리 기술 블로그">\n<!-- End Jekyll SEO tag -->\n<link rel="stylesheet" href="/assets/main.css?ver={{ site.version }}"><link type="application/atom+xml" rel="alternate" href="http://thefarmersfront.github.io/feed.xml" title="컬리 기술 블로그"></head>\n<body><header class="site-header" role="banner">\n\n  <div class="wrapper"><a class="site-title" rel="author" href="/">컬리 기술 블로그</a><nav class="site-nav">\n        <input type="checkbox" id="nav-trigger" class="nav-trigger">\n        <label for="nav-trigger">\n          <span class="menu-icon">\n            <svg viewBox="0 0 18 15" width="18px" height="15px">\n              <path d="M18,1.484c0,0.82-0.665,1.484-1.484,1.484H1.484C0.665,2.969,0,2.304,0,1.484l0,0C0,0.665,0.665,0,1.484,0 h15.032C17.335,0,18,0.665,18,1.484L18,1.484z M18,7.516C18,8.335,17.335,9,16.516,9H1.484C0.665,9,0,8.335,0,7.516l0,0 c0-0.82,0.665-1.484,1.484-1.484h15.032C17.335,6.031,18,6.696,18,7.516L18,7.516z M18,13.516C18,14.335,17.335,15,16.516,15H1.484 C0.665,15,0,14.335,0,13.516l0,0c0-0.82,0.665-1.483,1.484-1.483h15.032C17.335,12.031,18,12.695,18,13.516L18,13.516z"></path>\n            </svg>\n          </span>\n        </label>\n\n      </nav></div>\n</header>\n<main class="page-content" aria-label="Content">\n      <div class="wrapper">\n        <style type="text/css" media="screen">\n  .container {\n    margin: 10px auto;\n    max-width: 600px;\n    text-align: center;\n  }\n  h1 {\n    margin: 30px 0;\n    font-size: 4em;\n    line-height: 1;\n    letter-spacing: -1px;\n  }\n</style>\n\n<div class="container">\n  <h1>404</h1>\n\n  <p><strong>Page not found :(</strong></p>\n  <p>이 페이지를 보고 있는 당신께 심심한 위로를 전달합니다.</p>\n</div>\n\n      </div>\n    </main><footer class="site-footer h-card">\n  <data class="u-url" href="/"></data>\n\n  <div class="wrapper">\n\n    <h2 class="footer-heading">컬리 기술 블로그</h2>\n\n    <div class="footer-col-wrapper">\n      <div class="footer-col footer-col-1">\n      </div>\n\n      <div class="footer-col footer-col-2"><ul class="social-media-list"></ul>\n      </div>\n\n    </div>\n\n  </div>\n\n</footer>\n\n\n\n</body></html>'

    plain_text = extract_plain_text(html)

    assert (
        "컬리 기술 블로그\n404\nPage not found :(\n이 페이지를 보고 있는 당신께 심심한 위로를 전달합니다."
        == plain_text
    )

    with pytest.raises(ValidationError, match="soft_block:not found"):
        validate_plain_text(plain_text)


def test_validate_short_SPA_error_pipeline():
    html = """
<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"><meta http-equiv="X-UA-Compatible" content="IE=Edge"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="360"></head><body><div class="main-wrapper" role="main"><div class="main-content"><noscript><div class="h2"><span id="challenge-error-text">Enable JavaScript and cookies to continue</span></div></noscript></div></div></body></html>
"""

    plain_text = extract_plain_text(html)

    assert "Enable JavaScript and cookies to continue" == plain_text

    with pytest.raises(
        ValidationError,
        match="content_too_short",
    ):
        validate_plain_text(plain_text)


def test_validate_medium_too_many_request_error_pipeline():
    html = """
<!DOCTYPE html><html lang="en" data-rh="lang"><head><title>Medium</title></head><body><div id="root"><div><section><div><div>500</div></div><div><h2>Apologies, but something went wrong on our end.</h2><div>Refresh the page, check <a href="https://status.medium.com" rel="noopener follow">Medium's site status</a>, or <a href="https://medium.com/browse/top" rel="noopener follow">find something interesting to read</a>.</div></div></section></div></div></body></html>
"""
    plain_text = extract_plain_text(html)

    assert (
        plain_text
        == "500\nApologies, but something went wrong on our end.\nRefresh the page, check\nMedium's site status\n, or\nfind something interesting to read\n."
    )
