"""API 계약 문서와 실제 라우트 집합을 대조한다.

계약 문서의 엔드포인트 표에서 `메서드 | 경로`를 뽑아 FastAPI 앱의
라우트와 비교한다. 문서에만 있으면 구현 누락, 앱에만 있으면 문서 누락이다.

    uv run python scripts/check_routes.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "docs" / "architecture" / "api-contract.md"
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

    # `app.routes`를 직접 걷지 않는다. fastapi>=0.13x는 `include_router()`가
    # 만든 서브라우터를 지연 래퍼(`_IncludedRouter`)로 감싸 두고 실제 경로는
    # 요청 시점에야 계산한다 — 내부 구현이라 버전마다 또 바뀔 수 있다.
    # `openapi()`는 그 해석을 이미 끝낸, 공개돼 있고 안정적인 결과다.
    schema = create_app().openapi()
    routes = {
        normalize(method, path)
        for path, methods in schema["paths"].items()
        for method in methods
        if method.upper() not in {"HEAD", "OPTIONS"}
    }
    # 리다이렉트 응답이라 Swagger try-it-out 대상이 아니다 — 셋 다 include_in_schema=False.
    routes.add(("GET", "/health"))
    routes.add(("GET", f"{PREFIX}/auth/google/login"))
    routes.add(("GET", f"{PREFIX}/auth/google/callback"))
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
    print(f"라우트 {len(docs)}개가 API 계약과 일치한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
