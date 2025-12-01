from __future__ import annotations

import logging

import pytest

from summary_worker.app.parser import extract_plain_text, extract_thumbnail
from summary_worker.app.renderer import render_html
from summary_worker.app.validator import validate_plain_text, ContentValidationError


logger = logging.getLogger(__name__)


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

    with pytest.raises(ContentValidationError, match="soft_block:not found"):
        validate_plain_text(plain_text)


def test_validate_short_SPA_error_pipeline():
    html = """
<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"><meta http-equiv="X-UA-Compatible" content="IE=Edge"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box;margin:0;padding:0}html{line-height:1.15;-webkit-text-size-adjust:100%;color:#313131;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif,"Apple Color Emoji","Segoe UI Emoji","Segoe UI Symbol","Noto Color Emoji"}body{display:flex;flex-direction:column;height:100vh;min-height:100vh}.main-content{margin:8rem auto;padding-left:1.5rem;max-width:60rem}@media (width <= 720px){.main-content{margin-top:4rem}}.h2{line-height:2.25rem;font-size:1.5rem;font-weight:500}@media (width <= 720px){.h2{line-height:1.5rem;font-size:1.25rem}}#challenge-error-text{background-image:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMiIgaGVpZ2h0PSIzMiIgZmlsbD0ibm9uZSI+PHBhdGggZmlsbD0iI0IyMEYwMyIgZD0iTTE2IDNhMTMgMTMgMCAxIDAgMTMgMTNBMTMuMDE1IDEzLjAxNSAwIDAgMCAxNiAzbTAgMjRhMTEgMTEgMCAxIDEgMTEtMTEgMTEuMDEgMTEuMDEgMCAwIDEtMTEgMTEiLz48cGF0aCBmaWxsPSIjQjIwRjAzIiBkPSJNMTcuMDM4IDE4LjYxNUgxNC44N0wxNC41NjMgOS41aDIuNzgzem0tMS4wODQgMS40MjdxLjY2IDAgMS4wNTcuMzg4LjQwNy4zODkuNDA3Ljk5NCAwIC41OTYtLjQwNy45ODQtLjM5Ny4zOS0xLjA1Ny4zODktLjY1IDAtMS4wNTYtLjM4OS0uMzk4LS4zODktLjM5OC0uOTg0IDAtLjU5Ny4zOTgtLjk4NS40MDYtLjM5NyAxLjA1Ni0uMzk3Ii8+PC9zdmc+");background-repeat:no-repeat;background-size:contain;padding-left:34px}@media (prefers-color-scheme: dark){body{background-color:#222;color:#d9d9d9}}</style><meta http-equiv="refresh" content="360"></head><body><div class="main-wrapper" role="main"><div class="main-content"><noscript><div class="h2"><span id="challenge-error-text">Enable JavaScript and cookies to continue</span></div></noscript></div></div><script>(function(){window._cf_chl_opt = {cvId: '3',cZone: 'medium.com',cType: 'managed',cRay: '9a73633f1b0a018f',cH: 'kEjpCwT6S9v7b3xSQ8sqczdxGutTZFc0n5gYRzUvVBk-1764600529-1.2.1.1-Llxvc9oXcIIWTgjrBWDIm_Iq.ieZ7YhVrkJmc_AM9gscnVa0UoAjpcDLzeGVwSwY',cUPMDTk:"/musinsa-tech/ai%EC%99%80%EC%9D%98-%EC%84%B1%EA%B3%B5%EC%A0%81%EC%9D%B8-%EC%B2%AB-co-work-%EB%B0%94%EC%9D%B4%EB%B8%8C-%EC%BD%94%EB%94%A9%EC%9C%BC%EB%A1%9C-%ED%83%84%EC%83%9D%EB%90%9C-%EB%A7%9E%EC%B6%A4%ED%98%95-testcase-management-system-29tms-74062a620119?__cf_chl_tk=aIO09mr5gtcVAwFkHLBdmL5sfHyZBTZCTBQ12Q9T59c-1764600529-1.0.1.1-t.b8gIagRRgu68g43XJ5JGI4.lJeWxN88HZ72hxFQYs",cFPWv: 'b',cITimeS: '1764600529',cTplC:0,cTplV:5,cTplB: '0',fa:"/musinsa-tech/ai%EC%99%80%EC%9D%98-%EC%84%B1%EA%B3%B5%EC%A0%81%EC%9D%B8-%EC%B2%AB-co-work-%EB%B0%94%EC%9D%B4%EB%B8%8C-%EC%BD%94%EB%94%A9%EC%9C%BC%EB%A1%9C-%ED%83%84%EC%83%9D%EB%90%9C-%EB%A7%9E%EC%B6%A4%ED%98%95-testcase-management-system-29tms-74062a620119?__cf_chl_f_tk=aIO09mr5gtcVAwFkHLBdmL5sfHyZBTZCTBQ12Q9T59c-1764600529-1.0.1.1-t.b8gIagRRgu68g43XJ5JGI4.lJeWxN88HZ72hxFQYs",md: 'licBX5mKsHMyltS2bD46Ex4rWP4So.e5Bd0xj0CndWU-1764600529-1.2.1.1-nEJ2VMgKq_dvu13DB238kEOyjLv0tgeuXMZKtCrs_ErlvtD_9wfACD1kWMHKjZd_GZ2qojJluFziY61GAbz8bxBwfVaTW7VJvEhGktyOQ_B4E78GZweVIAm64u8i2vDMODdhqfSSbxqIzRwChfQw2iYBFYnDljwPD070hl5wpaMUCuxH6djywT9RRXiS.U0b2yvHlJX5H6Hhy2s.DVNlDq_iiEJxoxl1KpGe5NkDVG8hIFTAnvzJwxmLaOLfA8jHI0ySDLE8XQRaq3LSbGkmTJb89QuDKqzqx9LzuuEeW27BADnRjSY4H5AtDpwt9R.yqyHxaf1iZiHXKrRo14esHmBuwu9QQ0TNY6u9fKQgj8g93pn8kwC4dACHwdiMcz5_pNBImwhKz31FjK8IUt_VuWMSxsqc.t.rAaCSmdTtLDjh3TbKrDYqziakt4YG4kc4T0yr1UeJtM7Pzpwou9jniDStApzWyAI3KntDzBtnzNEcFRbfqSMxe1m4YvFs5YQAjBdBlvu6sjkE7LYLIgOyqhCCFiyalKn_g9ti89.Fx_ZMgyBQ5HtgOMxwGnM2oDi4OYBnzIyFn4x4L6bWauWNofvrpI8o7NmlGzCcNOZdZO0dLB39hAllMaZHtnTHDXDLk9.kBKaeuwhQWAIT1IadxyQtjxFVdpZAd4N_e894bVgpU0u1i6BdzJuZT7HWCix02.UsvgnhiYkMwYSsh.bQN7CHFlLTjDg6TIvWuJ4w52qRzdfDACvV.0YSS6w4EYmbe60lZZC24ySfNTtQrFOspH2oCvkS8.ANyqbZT2kvnPbxKEV_DszgzgUOKvGAykjpFNzSisPru0a3Ha8x9vqTh_Xd_E_cqcFHXwt9XWqa.sSYyOrvb0Xf1nXMDgZMFIXJMk3Utan4FmsbP2PEX.cfxG2KEeU6w9bIM0HoyKBCPpiFI2u2lPSoTcOTY4Uf5GnCRMcxznlOuYW3XVqHTOJnpVmNknQM3v_NkJBVY1CQqulGCGq7zJIiRb3hcBR3FQYmttwOzsEpDsjnyixHjEuKdK6kUMhfF07xBR9O7Lfy8Ar4gyMAopfl_KTL.5UzUJuZJdTudLjnTXqh6OqpczO3Q4uCUo5W8x9f_RV5.rrDI95DBKEwjVCfoL3xJv3wpNIvZ0.rvBUjmZcXOVOY8_ZkPpJBCPxUr849IsOc0inM5Cj35yXc4z_FO8whe9jyQrmetiuXNakF5QKviXv0TkmsEo.QsdatiZuVvUsrhs1_HQA',mdrd: 'pjypUoZqX0u_M6xzf8Latoba3vjgFzGIJp8oRPDWOJc-1764600529-1.2.1.1-M3qsE_RDfpRw0VlhIt4VMEjYYUULDm9u1fh2fYbGy5LwxTa7Sj7JngYvNDdAhBTgzKFodbPu56Uj.qhHPLK66KPGV3iZUbfap3CwKA2bNeeyjBqB77Ce.ufk99SLC31LQL57q5o0J_n4yQMijhvlwqaLHgrZ34AWDA2TdPvVMiivtdx7uWrLk2V_5m2EwZlEYVxTqnsyptr.Un8sF_r8LAedEyRLwwP3O_5Kl.sVLoib.0GHf3ICyQ8b9fQJoVqinn_jrkFahVjV2rvci4fiaaynEvHeTQxEBF9ntI2Fh4I3XlXonIdxknTgc0_MBc6Q0csbW9Ue3oWz1S_eLwQ_TFEYiRxmXV8WHWbNa8WcxcD69fsm.FVHL5eJLMizI0KoJ88iErETvXN.cjaiYZLDGLa56ldsPQzYhiDCN8Ern95PKUiijA5LWrniwAGX29C9OXgIXVGWX.6sgg2STU._8AVDoXNE3vktKBis5iTAkaLxxWM1H0KhtOohBZDrjMdZ_9umUdcCz_SVfV5eLVXyGIh0o9QuAatAJHfJ4lOum5U9TDh9jiYbDICn9_PRK.K7iU89pjzVQHZg1pmDRCQfIxnsp2De00hvQ2US6SBMfPZzyflvKMsFP1_If7N2yo4Ui7mXzCuKLRtPcsPAameeg09JBfqb9jov9GHMorf2UmA0jBOJaslj1xAwI.bjy7qS83PQKI3z8NPI8pzCZ.YKtOcTndjOW9GU7ilpdkP.CyePKkrL7LHcEa6_Yc89EAItRI5DS.n8eswSKwEJL9YqECjNFnML95OQPYLj3x4QiVaWo1Hlk..v1BGbYOB8JKhWE0hhGjbJZ46MWtQi9enUxYcjFqx9MCg8uHQJsvmqn9P.zFJUoANbYJnXVKARW76lNCS7wY8Yy0UKu7aARPKxtNkJx.Z80so0OA35mqOVJXQZvnO8qIKNLt0mP052LYfeQiAyk.tMDnXuWYQSyfoGXhMYz.hNd.8B9EfNjxqH0zi2OMw34ExmCCYunTqrqpzdwkJdBtDKx1Zi8nkjx_qAJndxvloHz2rfjII6WVQVpnO3aruhReuNpQacWjs2h7qYkfcjPp42WkdsSBZ6EI6SGfGdKNVi1gcFGq6FWsaWr8lCLRy2iK1eLsB.bCqZ1Js.BSrCG5UlafD1XrNMvf2IXVf2Bqw6EK9_pSm59g_QVk5Yti1X6KIdNncnoYHKLUcZvwaLCkW7NVqm4SBz0KnKBIcXLWx1rPo2y1cz_LUzlgFT5hoarTAPH8MYSg9b6oV2kGFDTSpy31qr2nU9.bwbXCUXSU_SgTwTZgr57I_EZ9MsznscjHn1gRj20PfGgDMNL8Zp.4Oj1.JPufP1XkfwBWcOjuVQca9_7Bj47ez5n0vSDJMYfKLWVUPXIHlFbpoKBkC3l5iSJ7iP0VqBS7ZlDk6NrWKXoMEGSvsFP7tr2N186oCrjHmlLGakyJFrmG8q_82LJlZF0WOrK7A1lwUDfB0s8GY8kwWLKwY6igTWL9x1m90GF10oKxEes11Mh2TXS6nNuEutFQL1QPJ5k40DkdIxvM.cXRmboYyT6VmuzJm0Zit_C0JfBV357N9_AuRzXTJpS.DgFuu0s9EcXGNT9KssGTBLq5mCiBwleuO6mwg9RUZfptPnB_jqK90Q6FgFGwzLjDUy.S4AByOUPPUAeSdcHeY0rAPM48MzeWzyvqsYhlqTiY93of2eo3rseFznxtPn4gF3c7FKPThPWtzwoUAH.W_L4BZDfbnPlqdM1Q2UvVS6WODTQuGCBmwJsSLL8MapDtgFvhL0tOBsaQwW3DOMLTftxvB3C1TULsvh6e3GT0pyjAnxpmIb52p4Y0Ray4IJYAmK4IwjXucbw0ASoUbsj9B6ddIBHa4T7tYSQuzjKUdg5eiPeddy2HYW0WnzpqN3y8PEhOq38YYH_ULiBBmjq5c4gOfUzruL2iehh_pMu6EpynYf3ZD0SuR0GnfNUVkUwNQbYWF2.hRSTDKPJP3yuOGlx92FCiMM3ZYp2umCcWOQngItiWqx5jx.vVr_RKbcqNSWhwq.bM.stBN5hEYRKUR25pmnZB5w1FZJxBRVHkiXrXaZkVfBGGB_6a.rbH3.CNv4UAweoed1es038R5QnmE0LPCXGNaEgfFvWHRMxl98MgDst8wemXbTKm7_E75v91e8Kv4dpM7y750HB9DXa5HAZ_xPPhl2UzLpuhzxQ2Xz.jQn2nHIzREIXIkkDCLmLwGMcmcP_Qv6p3esXRBmbClb53efRkMSOEhU1R00PGTf3cvX0aAHRi_Q0EjIpiz.BXONolfjSrYQ5YXMw3cjsPmXOOFt_JuugjqV8KslpU_.2kGf.4ByRMN3Nv_K9bfTEOQIgDS0NxMnc79ZaqhIEwtibwj6gjkEI5btdWi8TfL.5g4SK7UqnoFMr7wTgeNCMm8vedqPZZ63M3NV9b2Tdh3qGYngpCrjvw0N7vo',};var a = document.createElement('script');a.src = '/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1?ray=9a73633f1b0a018f';window._cf_chl_opt.cOgUHash = location.hash === '' && location.href.indexOf('#') !== -1 ? '#' : location.hash;window._cf_chl_opt.cOgUQuery = location.search === '' && location.href.slice(0, location.href.length - window._cf_chl_opt.cOgUHash.length).indexOf('?') !== -1 ? '?' : location.search;if (window.history && window.history.replaceState) {var ogU = location.pathname + window._cf_chl_opt.cOgUQuery + window._cf_chl_opt.cOgUHash;history.replaceState(null, null,"/musinsa-tech/ai%EC%99%80%EC%9D%98-%EC%84%B1%EA%B3%B5%EC%A0%81%EC%9D%B8-%EC%B2%AB-co-work-%EB%B0%94%EC%9D%B4%EB%B8%8C-%EC%BD%94%EB%94%A9%EC%9C%BC%EB%A1%9C-%ED%83%84%EC%83%9D%EB%90%9C-%EB%A7%9E%EC%B6%A4%ED%98%95-testcase-management-system-29tms-74062a620119?__cf_chl_rt_tk=aIO09mr5gtcVAwFkHLBdmL5sfHyZBTZCTBQ12Q9T59c-1764600529-1.0.1.1-t.b8gIagRRgu68g43XJ5JGI4.lJeWxN88HZ72hxFQYs"+ window._cf_chl_opt.cOgUHash);a.onload = function() {history.replaceState(null, null, ogU);}}document.getElementsByTagName('head')[0].appendChild(a);}());</script></body></html>
"""

    plain_text = extract_plain_text(html)
    print(len(plain_text))

    assert "Enable JavaScript and cookies to continue" == plain_text

    with pytest.raises(
        ContentValidationError,
        match="content_too_short",
    ):
        validate_plain_text(plain_text)
