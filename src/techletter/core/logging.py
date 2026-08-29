"""구조화 JSON 로깅.

현행과 달라지는 점(09 §3.1, ISSUE-014):
- 타임스탬프가 **UTC ISO-8601 + 밀리초 + `Z`**. 현행은 TZ 없는 로컬 시각이라
  데이터(UTC)와 로그(KST)가 섞여 있었다.
- **요청 본문을 로깅하지 않는다.** 현행 미들웨어가 본문 1024자를 남겨
  `/login-sessions`의 JWT가 로그에 그대로 들어갔다.
- `request_id`/`trace_id`/`job_id`를 contextvar로 전파해 HTTP→잡→워커를 잇는다.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

from techletter.core.time import to_iso_z, utcnow

__all__ = ["bind_context", "clear_context", "get_logger", "setup_logging"]

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)

_CONTEXT_VARS = {"request_id": _request_id, "trace_id": _trace_id, "job_id": _job_id}

# LogRecord의 기본 속성. 이 목록에 없는 extra만 payload로 내보낸다.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def bind_context(**values: str | None) -> None:
    """현재 컨텍스트에 request_id/trace_id/job_id를 설정한다."""
    for key, value in values.items():
        var = _CONTEXT_VARS.get(key)
        if var is not None:
            var.set(value)


def clear_context() -> None:
    for var in _CONTEXT_VARS.values():
        var.set(None)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": to_iso_z(utcnow()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service,
        }
        for key, var in _CONTEXT_VARS.items():
            value = var.get()
            if value:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", service: str = "techletter") -> None:
    """루트 로거를 JSON 핸들러 하나로 교체한다."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # uvicorn이 자체 핸들러를 붙이면 로그가 두 번 나온다.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
