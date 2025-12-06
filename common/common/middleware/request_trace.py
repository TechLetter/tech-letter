import logging
import time
import uuid
from typing import Callable, Awaitable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from urllib.parse import parse_qs


REQUEST_ID_HEADER = "X-Request-Id"
SPAN_ID_HEADER = "X-Span-Id"

# 노이즈를 줄이기 위해 로그에서 제외할 엔드포인트 경로 목록
IGNORED_LOG_PATHS: set[str] = {"/health"}


class RequestTraceMiddleware(BaseHTTPMiddleware):
    """공통 Request/Span ID 로그 미들웨어.

    - 들어오는 요청에서 X-Request-Id, X-Span-Id 를 읽고, 없으면 request_id만 새로 생성한다.
    - request.state 에 request_id, span_id 를 저장한다.
    - 응답 헤더에 동일한 값을 설정한다.
    - 최소한의 inbound/outbound 로그를 남긴다.
    """

    def __init__(self, app, logger: logging.Logger | None = None) -> None:  # type: ignore[override]
        super().__init__(app)
        self._logger = logger or logging.getLogger("request_trace")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id, span_id = self._extract_trace_ids(request)

        # 앱에서 사용할 수 있도록 state 에 저장
        request.state.request_id = request_id
        request.state.span_id = span_id

        # POST/PUT/PATCH/DELETE 의 경우 바디 스니펫을 미리 읽어 state 에 저장한다.
        raw_body: str | None = None
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                body_bytes = await request.body()
            except Exception:
                body_bytes = b""
            if body_bytes:
                text = body_bytes.decode("utf-8", errors="replace")
                max_len = 1024
                if len(text) > max_len:
                    text = text[:max_len]
                raw_body = text

        request.state.request_body = raw_body

        should_log = self._should_log_request(request)

        start = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            if should_log:
                duration = time.monotonic() - start
                self._log_exception(request, request_id, span_id, duration)
            raise

        self._set_response_headers(response, request_id, span_id)

        if should_log:
            duration = time.monotonic() - start
            self._log_completed(request, response, request_id, span_id, duration)

        return response

    def _extract_trace_ids(self, request: Request) -> tuple[str, str]:
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if not request_id:
            request_id = self._generate_request_id()

        span_id = request.headers.get(SPAN_ID_HEADER) or "0"
        return request_id, span_id

    def _should_log_request(self, request: Request) -> bool:
        # noisy 한 헬스체크 등 특정 엔드포인트는 로그에서 제외해 노이즈를 줄인다.
        return request.url.path not in IGNORED_LOG_PATHS

    def _build_log_extra(
        self,
        request: Request,
        request_id: str,
        span_id: str,
        status: int | None = None,
        duration: float | None = None,
    ) -> dict[str, object]:
        extra: dict[str, object] = {
            "request_id": request_id,
            "span_id": span_id,
            "method": request.method,
            "path": request.url.path,
        }

        query = request.url.query
        if query:
            parsed = parse_qs(query, keep_blank_values=True)
            if parsed:
                extra["query_params"] = {
                    key: values[0] if len(values) == 1 else values
                    for key, values in parsed.items()
                }

        body = getattr(request.state, "request_body", None)
        if body:
            extra["body"] = body

        if status is not None:
            extra["status"] = status

        if duration is not None:
            extra["duration"] = f"{duration * 1000:.3f}ms"

        return extra

    def _log_completed(
        self,
        request: Request,
        response: Response,
        request_id: str,
        span_id: str,
        duration: float,
    ) -> None:
        self._logger.info(
            "completed request",
            extra=self._build_log_extra(
                request,
                request_id,
                span_id,
                status=response.status_code,
                duration=duration,
            ),
        )

    def _log_exception(
        self,
        request: Request,
        request_id: str,
        span_id: str,
        duration: float | None = None,
    ) -> None:
        self._logger.exception(
            "request failed",
            extra=self._build_log_extra(
                request,
                request_id,
                span_id,
                duration=duration,
            ),
        )

    def _set_response_headers(
        self,
        response: Response,
        request_id: str,
        span_id: str,
    ) -> None:
        response.headers.setdefault(REQUEST_ID_HEADER, request_id)
        response.headers.setdefault(SPAN_ID_HEADER, span_id)

    def _generate_request_id(self) -> str:
        return uuid.uuid4().hex
