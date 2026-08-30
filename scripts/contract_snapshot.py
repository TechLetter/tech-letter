#!/usr/bin/env python3
"""API 응답 '구조'를 캡처해 골든 스냅샷으로 저장한다.

값이 아니라 **모양**(키·타입·null 여부·봉투)을 기록해, 이후 diff를 떠서
"의도한 변경만 일어났는지" 심사하는 데 쓴다. 완전 일치를 요구하지는 않는다.

사용:
    BASE_URL=https://tech-letter.duckdns.org TOKEN=<jwt> ADMIN_TOKEN=<jwt> \
        python3 contract_snapshot.py --out ./snapshots

안전장치: GET 요청만 보낸다. 운영 데이터를 변경하는 요청은 보내지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

OID = re.compile(r"^[0-9a-f]{24}$")
DT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
URL = re.compile(r"^https?://")


def norm(v, depth=0):
    """값을 타입 토큰으로 치환해 구조만 남긴다. null은 보존한다."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "<bool>"
    if isinstance(v, int):
        return "<int>"
    if isinstance(v, float):
        return "<float>"
    if isinstance(v, str):
        if OID.match(v):
            return "<oid>"
        if DT.match(v):
            return "<datetime>"
        if URL.match(v):
            return "<url>"
        return "<str>"
    if isinstance(v, list):
        if not v:
            return []
        merged = {}
        scalar = None
        for item in v[:5]:
            n = norm(item, depth + 1)
            if isinstance(n, dict):
                for k, val in n.items():
                    if k not in merged or merged[k] is None:
                        merged[k] = val
            else:
                scalar = n
        return [merged] if merged else [scalar]
    if isinstance(v, dict):
        return {k: norm(v[k], depth + 1) for k in sorted(v)}
    return f"<{type(v).__name__}>"


def fetch(base, path, token=None, headers=None) -> dict[str, object]:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, val in (headers or {}).items():
        req.add_header(k, val)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=30) as r:
            body, status, ctype = r.read(), r.status, r.headers.get("Content-Type", "")
            loc = r.headers.get("Location")
    except urllib.error.HTTPError as e:
        body, status, ctype = e.read(), e.code, e.headers.get("Content-Type", "")
        loc = e.headers.get("Location")
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    out: dict[str, object] = {"status": status, "content_type": ctype.split(";")[0].strip()}
    if loc:
        # 리다이렉트 목적지는 쿼리 키만 남긴다(세션 값 노출 방지)
        p = urllib.parse.urlparse(loc)
        out["location"] = {"path": p.path, "query_keys": sorted(urllib.parse.parse_qs(p.query))}
    if body:
        try:
            out["body"] = norm(json.loads(body))
        except Exception:
            out["body"] = f"<non-json:{len(body)}bytes>"
    else:
        out["body"] = None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="snapshots")
    args = ap.parse_args()

    base = os.environ.get("BASE_URL", "https://tech-letter.duckdns.org")
    tok = os.environ.get("TOKEN")
    admin = os.environ.get("ADMIN_TOKEN") or tok
    post_id = os.environ.get("SAMPLE_POST_ID", "")
    blog_id = os.environ.get("SAMPLE_BLOG_ID", "")

    # (라벨, 경로, 토큰, 추가헤더)
    cases: list[tuple[str, str, str | None, dict | None]] = [
        ("health", "/health", None, None),
        ("posts__anon", "/api/v1/posts?page=1&page_size=2&status_ai_summarized=true", None, None),
        ("posts__auth", "/api/v1/posts?page=1&page_size=2&status_ai_summarized=true", tok, None),
        ("posts__empty_category", "/api/v1/posts?page=1&page_size=2&categories=", None, None),
        (
            "posts__repeated_tags",
            "/api/v1/posts?page=1&page_size=2&tags=Kafka&tags=React",
            None,
            None,
        ),
        ("posts__bad_page", "/api/v1/posts?page=abc&page_size=xyz", None, None),
        (
            "posts__date_only",
            "/api/v1/posts?published_from=2026-01-01&published_to=2026-08-01&page_size=2",
            None,
            None,
        ),
        ("posts__bad_date", "/api/v1/posts?published_from=nope", None, None),
        ("posts_detail", f"/api/v1/posts/{post_id}", None, None),
        ("posts_detail__missing", "/api/v1/posts/000000000000000000000000", None, None),
        ("posts_bookmarks", "/api/v1/posts/bookmarks?page=1&page_size=2", tok, None),
        ("blogs", "/api/v1/blogs?page=1&page_size=2", None, None),
        ("filters_categories", "/api/v1/filters/categories", None, None),
        ("filters_tags", "/api/v1/filters/tags", None, None),
        ("filters_blogs", "/api/v1/filters/blogs", None, None),
        ("filters_categories__scoped", f"/api/v1/filters/categories?blog_id={blog_id}", None, None),
        ("trends_rising", "/api/v1/trends/rising?period=180d&limit=3", None, None),
        ("trends_rising__bad_period", "/api/v1/trends/rising?period=999d", None, None),
        ("trends_rising__bad_limit", "/api/v1/trends/rising?limit=99", None, None),
        ("trends_series", "/api/v1/trends/series?tags=LLM&period=180d&interval=week", None, None),
        (
            "trends_series__bad_interval",
            "/api/v1/trends/series?tags=LLM&interval=fortnight",
            None,
            None,
        ),
        ("trends_posts", "/api/v1/trends/posts?tags=LLM&period=180d&page_size=2", None, None),
        ("users_profile", "/api/v1/users/profile", tok, None),
        ("users_profile__no_header", "/api/v1/users/profile", None, None),
        ("users_profile__basic", "/api/v1/users/profile", None, {"Authorization": "Basic zzz"}),
        (
            "users_profile__empty_token",
            "/api/v1/users/profile",
            None,
            {"Authorization": "Bearer  "},
        ),
        (
            "users_profile__bad_token",
            "/api/v1/users/profile",
            None,
            {"Authorization": "Bearer not.a.jwt"},
        ),
        ("chatbot_sessions", "/api/v1/chatbot/sessions?page=1&page_size=2", tok, None),
        (
            "chatbot_sessions__missing",
            "/api/v1/chatbot/sessions/000000000000000000000000",
            tok,
            None,
        ),
        ("chatbot_suggested", "/api/v1/chatbot/suggested-questions", None, None),
        ("auth_google_login", "/api/v1/auth/google/login", None, None),
        ("admin_posts", "/api/v1/admin/posts?page=1&page_size=2", admin, None),
        (
            "admin_posts__filtered",
            "/api/v1/admin/posts?page=1&page_size=2&status_ai_summarized=false",
            admin,
            None,
        ),
        ("admin_blogs", "/api/v1/admin/blogs?page=1&page_size=2", admin, None),
        ("admin_users", "/api/v1/admin/users?page=1&page_size=2", admin, None),
        ("admin_suggested", "/api/v1/admin/chatbot/suggested-questions", admin, None),
        ("admin_posts__forbidden", "/api/v1/admin/posts", None, None),
    ]

    os.makedirs(args.out, exist_ok=True)
    summary = []
    for label, path, token, headers in cases:
        if "{" in path or path.endswith("/"):
            continue
        res = fetch(base, path, token, headers)
        req_path = re.sub(r"/[0-9a-f]{24}", "/{id}", path.split("?")[0])
        res["_request"] = {
            "path": req_path,
            "authed": bool(token or (headers or {}).get("Authorization")),
        }
        with open(os.path.join(args.out, f"{label}.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1, sort_keys=True)
        st = res.get("status", res.get("error"))
        summary.append((label, st))
        print(f"  {label:34} -> {st}", flush=True)

    with open(os.path.join(args.out, "_index.json"), "w", encoding="utf-8") as f:
        json.dump({"base_url_kind": "prod", "cases": dict(summary)}, f, indent=1, sort_keys=True)
    ok = sum(1 for _, s in summary if isinstance(s, int) and s < 500)
    print(f"\n{ok}/{len(summary)} 캡처 (5xx/에러 제외)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
