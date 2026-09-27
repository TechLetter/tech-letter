"""분당 호출량 제한."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

__all__ = ["MinuteRateLimiter"]


class MinuteRateLimiter:
    """최근 1분 동안 보낸 양(요청·청크)을 `per_minute` 이하로 묶는다.

    구글 무료 등급은 분당 한도(RPM)를 넘기면 429를 준다. 임베딩은 배치 안의 텍스트
    하나하나를 요청 한 번으로 세고(RPM 100), 요약 모델은 3 Flash 5회·3.5 Flash Lite
    15회다. 429는 재시도·폴백을 부르니 넘기기 전에 기다리는 편이 싸다.
    `per_minute`가 0 이하면 제한하지 않는다. 프로세스 안에서만 센다.
    """

    WINDOW_SECONDS = 60.0

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._sent: deque[tuple[float, int]] = deque()
        self._used = 0
        self._lock = asyncio.Lock()

    @property
    def per_minute(self) -> int:
        return self._per_minute

    def _expire(self, now: float) -> None:
        while self._sent and now - self._sent[0][0] >= self.WINDOW_SECONDS:
            self._used -= self._sent.popleft()[1]

    async def acquire(self, count: int) -> None:
        """`count`개를 보내도 한도 안에 들 때까지 기다린 뒤 장부에 적는다."""
        if self._per_minute <= 0:
            return
        count = min(count, self._per_minute)
        async with self._lock:
            now = self._clock()
            self._expire(now)
            while self._used + count > self._per_minute:
                await self._sleep(self._sent[0][0] + self.WINDOW_SECONDS - now)
                now = self._clock()
                self._expire(now)
            self._sent.append((now, count))
            self._used += count
