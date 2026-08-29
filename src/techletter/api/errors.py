"""예외 → HTTP 응답 변환.

04 §1.3의 단일 에러 봉투 `{"error": {code, message, details?}}`로 통일한다.
FastAPI의 기본 422(RequestValidationError)도 400 `request.invalid`로 바꾼다 —
현행 게이트웨이가 422를 내지 않았고 프론트도 다루지 않기 때문이다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from techletter.core.errors import AppError, InternalError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)

_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "request.invalid",
    status.HTTP_401_UNAUTHORIZED: "auth.required",
    status.HTTP_403_FORBIDDEN: "auth.forbidden",
    status.HTTP_404_NOT_FOUND: "resource.not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "request.invalid",
    status.HTTP_409_CONFLICT: "resource.conflict",
    status.HTTP_429_TOO_MANY_REQUESTS: "llm.rate_limited",
    status.HTTP_503_SERVICE_UNAVAILABLE: "llm.unavailable",
}


def _body(code: str, message: str, details: dict | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    if exc.status >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error("app error", extra={"error_code": exc.code}, exc_info=exc)
    return JSONResponse(status_code=exc.status, content=exc.to_body())


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """422 대신 400 `request.invalid`. 필드 정보는 details로 넘긴다."""
    assert isinstance(exc, RequestValidationError)
    fields = [
        {"loc": ".".join(str(p) for p in e.get("loc", [])), "msg": e.get("msg", "")}
        for e in exc.errors()[:5]
    ]
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=_body("request.invalid", "요청 형식이 올바르지 않습니다.", {"fields": fields}),
    )


async def http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """FastAPI 내부에서 올라온 HTTPException도 같은 봉투로 맞춘다."""
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODES.get(exc.status_code, "internal.error")
    detail = exc.detail if isinstance(exc.detail, str) else None
    return JSONResponse(status_code=exc.status_code, content=_body(code, detail or code))


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """예상 못 한 예외. 내부 정보를 응답에 노출하지 않는다(ISSUE-009 #2)."""
    logger.error("unhandled error", exc_info=exc)
    fallback = InternalError()
    return JSONResponse(status_code=fallback.status, content=fallback.to_body())


def register_error_handlers(app: FastAPI) -> None:
    handlers: list[tuple[type[Exception] | int, Callable[[Request, Exception], Awaitable]]] = [
        (AppError, app_error_handler),
        (RequestValidationError, validation_error_handler),
        (StarletteHTTPException, http_error_handler),
        (Exception, unhandled_error_handler),
    ]
    for exc_type, handler in handlers:
        app.add_exception_handler(exc_type, handler)
