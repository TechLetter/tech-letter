"""요청 범위 토큰 계량."""

from __future__ import annotations

import asyncio

from techletter.core.llm.usage import record_usage, track_usage


async def test_usage_adds_up_across_calls_and_child_tasks() -> None:
    """라우터가 하위 태스크에서 불러도 같은 계량기에 쌓인다."""
    with track_usage() as meter:
        record_usage({"input_tokens": 100, "output_tokens": 20})
        await asyncio.create_task(asyncio.to_thread(lambda: None))
        await asyncio.create_task(_call({"input_tokens": 50, "output_tokens": 5}))

    assert (meter.input_tokens, meter.output_tokens, meter.calls) == (150, 25, 2)


async def _call(usage: dict) -> None:
    record_usage(usage)


def test_outside_a_request_nothing_is_recorded() -> None:
    record_usage({"input_tokens": 1})  # 예외 없이 무시된다

    with track_usage() as meter:
        pass

    assert meter.calls == 0
