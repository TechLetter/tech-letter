"""04 계약 문서와 실제 라우트 집합을 대조한다.

계약 문서의 엔드포인트 표(§4)에서 `메서드 | 경로`를 뽑아 FastAPI 앱의
라우트와 비교한다. 문서에만 있으면 구현 누락, 앱에만 있으면 문서 누락이다.

    uv run python scripts/check_routes.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "docs" / "plan" / "04-api-v2.md"
PREFIX = "/api/v1"

# 문서 표의 한 줄: | ➕ GET | `/admin/jobs` | ... |
ROW = re.compile(
    r"^\|\s*(?:[➕🔄✅❌]\s*)?(GET|POST|PUT|DELETE|PATCH)\s*\|\s*`([^`]+)`",
    re.MULTILINE,
)
# 문서는 `{id}`, 코드는 `{post_id}` 처럼 이름이 다를 수 있다. 자리만 비교한다.
PARAM = re.compile(r"\{[^}]+\}")

# 문서에 없지만 있어야 하는 것 / 문서에 있지만 라우트가 아닌 것.
DOC_ONLY_OK: set[tuple[str, str]] = set()
APP_ONLY_OK = {
    ("GET", "/health"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
    # 계약 문서에 없는 편의 경로. 어드민이 자동 비활성화된 블로그를 되살린다.
    ("POST", f"{PREFIX}/admin/blogs/{{}}/activate"),
    # 백필은 문서에 요약만 적혀 있으나 임베딩도 같은 모양으로 제공한다.
    ("POST", f"{PREFIX}/admin/backfill/embeddings"),
}


def normalize(method: str, path: str) -> tuple[str, str]:
    if not path.startswith(("/api/", "/health", "/docs", "/redoc", "/openapi")):
        path = f"{PREFIX}{path}"
    return method.upper(), PARAM.sub("{}", path).rstrip("/") or "/"


def documented() -> set[tuple[str, str]]:
    text = CONTRACT.read_text(encoding="utf-8")
    return {normalize(m, p) for m, p in ROW.findall(text)}


def implemented() -> set[tuple[str, str]]:
    os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/x")
    os.environ.setdefault("JWT_SECRET", "x" * 40)
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "c")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "s")
    os.environ.setdefault("GOOGLE_OAUTH_REDIRECT_URL", "http://localhost/cb")
    os.environ.setdefault("AUTH_LOGIN_SUCCESS_REDIRECT_URL", "http://localhost/ok")
    sys.path.insert(0, str(ROOT / "src"))

    from techletter.app import create_app

    routes: set[tuple[str, str]] = set()
    for route in create_app().routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.add(normalize(method, path))
    return routes


def main() -> int:
    docs, app = documented(), implemented()
    missing = sorted(docs - app - DOC_ONLY_OK)
    extra = sorted(app - docs - APP_ONLY_OK)

    for method, path in missing:
        print(f"MISSING  문서에는 있으나 구현되지 않음: {method} {path}")
    for method, path in extra:
        print(f"EXTRA    구현되었으나 문서에 없음:     {method} {path}")

    if missing or extra:
        print(f"\n불일치 {len(missing) + len(extra)}건 (문서 {len(docs)} · 앱 {len(app)})")
        return 1
    print(f"라우트 {len(docs)}개가 04 계약과 일치한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
