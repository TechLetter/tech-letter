"""게시물 링크를 중복 판정용 키로 정규화한다."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = ["normalize_link"]


_TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "_ga",
        "_gl",
        "ref_src",
        "yclid",
    }
)


def normalize_link(url: str) -> str:
    """URL의 표현 차이를 제거한 중복 판정 키를 돌려준다.

    피드에는 URL이 아닌 식별자가 들어오거나 파싱할 수 없는 값이 섞일 수
    있다. 그런 값까지 수집을 실패시키지 않도록 어떤 예외도 밖으로 내보내지
    않고, 원문의 바깥 공백만 제거해 돌려준다.
    """
    value = url.strip()
    if not value:
        return value

    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc or not parts.hostname:
            return value

        scheme = parts.scheme.lower()
        hostname = parts.hostname.lower()
        # www.를 없애면 서로 다른 호스트를 같은 글로 오인할 수 있다.
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"

        userinfo = ""
        if "@" in parts.netloc:
            userinfo = f"{parts.netloc.rsplit('@', 1)[0]}@"

        port = parts.port
        if port is not None and not (
            (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        ):
            hostname = f"{hostname}:{port}"
        netloc = f"{userinfo}{hostname}"

        path = parts.path or "/"
        if path != "/":
            path = path.rstrip("/") or "/"

        query_pairs = [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if not (key.lower().startswith("utm_") or key.lower() in _TRACKING_PARAMS)
        ]
        query_pairs.sort(key=lambda pair: pair[0])
        query = urlencode(query_pairs, doseq=True)
        return urlunsplit((scheme, netloc, path, query, ""))
    except Exception:
        # urlsplit의 잘못된 IPv6/포트 등 파싱 예외도 링크 하나 때문에 전체
        # 수집을 중단하지 않도록 원문을 안전한 fallback으로 사용한다.
        return value


_PAGE_SUFFIX = re.compile(r"\.(html?|php|aspx?)$", re.I)


def link_slug(url: str) -> str:
    """주소의 마지막 경로 조각. 도메인을 옮긴 같은 글인지 가늠하는 데 쓴다.

    `/2026/02/24/frame2-web.html`과 `/2026/02/25/frame2-web`은 같은 `frame2-web`이다
    (쏘카는 이전하면서 확장자를 떼고 날짜를 하루 옮겼다). 조각이 없으면 빈 문자열.
    """
    try:
        path = urlsplit(url.strip()).path
    except ValueError:
        return ""
    last = path.rstrip("/").rsplit("/", 1)[-1]
    return _PAGE_SUFFIX.sub("", last).lower()
