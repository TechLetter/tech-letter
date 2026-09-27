"""요청 하나가 쓴 LLM 토큰.

챗봇 답변 옆 (i)에 모델·토큰·응답 시간을 보여 준다. 라우터를 거쳐 여러 모델을
시도하고, 계획·질의 재작성·답변이 따로 호출되므로 호출 지점마다 반환값을 끌고
올라오는 대신 요청 범위의 계량기에 더한다. 계량기는 변경 가능한 객체라 라우터가
하위 태스크에서 호출해도(컨텍스트가 복사돼도) 같은 객체에 쌓인다.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

__all__ = ["UsageMeter", "record_usage", "track_usage"]


@dataclass(slots=True)
class UsageMeter:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, usage: dict[str, Any]) -> None:
        self.input_tokens += int(usage.get("input_tokens") or 0)
        self.output_tokens += int(usage.get("output_tokens") or 0)
        self.calls += 1


_current: ContextVar[UsageMeter | None] = ContextVar("llm_usage_meter", default=None)


@contextmanager
def track_usage() -> Iterator[UsageMeter]:
    meter = UsageMeter()
    token = _current.set(meter)
    try:
        yield meter
    finally:
        _current.reset(token)


def record_usage(usage: dict[str, Any] | None) -> None:
    """계량 중이 아니면(워커의 요약 등) 아무것도 하지 않는다."""
    meter = _current.get()
    if meter is not None and usage:
        meter.add(usage)
