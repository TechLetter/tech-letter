"""요청 추적 미들웨어.

`BaseHTTPMiddleware`가 아니라 **순수 ASGI**로 쓴다. `BaseHTTPMiddleware`는
요청 본문을 선행 소비해 버려서 SSE 스트리밍과 상성이 나쁘고, 로깅을 위해
바디에 손대면 JWT 같은 민감 값이 로그로 새어나갈 위험도 생긴다.

- `X-Request-Id`가 오면 그대로 쓰고, 없으면 생성한다. 응답에도 에코한다.
- **본문은 절대 읽지 않는다.**
- 쿼리의 검색어(`q`)는 가려서 남긴다. 개인정보처리방침에 "검색어는 저장하지 않는다"고
  약속했다(2026-09-27).
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode

from techletter.core.logging import bind_context, clear_context, get_logger

if TYPE_CHECKING:  # pragma: no cover
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = get_logger("techletter.request")

REQUEST_ID_HEADER = b"x-request-id"
SPAN_ID_HEADER = b"x-span-id"
_SKIP_PATHS = frozenset({"/health", "/metrics", "/favicon.ico"})
_REDACTED_PARAMS = frozenset({"q"})


def redact_query(raw: bytes) -> str:
    """로그에 남길 쿼리 문자열. 검색어처럼 이용자가 입력한 값은 `***`로 바꾼다."""
    text = raw.decode(errors="replace")
    if not text:
        return ""
    pairs = parse_qsl(text, keep_blank_values=True)
    if not any(key in _REDACTED_PARAMS for key, _ in pairs):
        return text[:200]
    safe = [(key, "***" if key in _REDACTED_PARAMS else value) for key, value in pairs]
    return urlencode(safe, safe="*")[:200]


class RequestTraceMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = (headers.get(REQUEST_ID_HEADER) or b"").decode() or uuid.uuid4().hex
        path: str = scope.get("path", "")
        method: str = scope.get("method", "")
        started = time.monotonic()
        status_code = 500

        bind_context(request_id=request_id)

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                raw = list(message.get("headers") or [])
                raw.append((REQUEST_ID_HEADER, request_id.encode()))
                raw.append((SPAN_ID_HEADER, b"0"))
                message["headers"] = raw
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if path not in _SKIP_PATHS:
                logger.info(
                    "completed request",
                    extra={
                        "method": method,
                        "path": path,
                        "query": redact_query(scope.get("query_string", b"")),
                        "status": status_code,
                        "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    },
                )
            clear_context()
