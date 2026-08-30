"""워커 프로세스 런타임 — heartbeat와 graceful shutdown."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from techletter.core.logging import get_logger
from techletter.core.time import utcnow

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Coroutine
    from typing import Any

__all__ = ["HEARTBEAT_PATH", "Heartbeat", "run_with_shutdown"]

logger = get_logger(__name__)

HEARTBEAT_PATH = Path("/tmp/techletter-heartbeat")


class Heartbeat:
    """루프가 살아 있다는 표시. compose healthcheck가 파일 mtime을 본다."""

    def __init__(self, path: Path = HEARTBEAT_PATH, *, min_interval_seconds: float = 5.0) -> None:
        self._path = path
        self._min_interval = min_interval_seconds
        self._last = 0.0

    def touch(self) -> None:
        now = utcnow().timestamp()
        if now - self._last < self._min_interval:
            return
        self._last = now
        try:
            self._path.write_text(str(int(now)))
        except OSError:
            logger.warning("heartbeat write failed", extra={"path": str(self._path)})


async def run_with_shutdown(
    main: Callable[[], Coroutine[Any, Any, None]],
    *,
    on_signal: Callable[[], None],
    grace_seconds: float = 25.0,
) -> None:
    """SIGTERM/SIGINT를 받으면 `on_signal`로 정지를 알리고 drain을 기다린다.

    `on_signal`은 보통 러너의 `request_stop`이다. 신호를 받은 뒤에도 처리 중인
    잡은 끝까지 돌려보내고, `grace_seconds` 안에 끝나지 않으면 취소한다.
    compose의 `stop_grace_period: 30s`보다 짧게 잡아 SIGKILL 전에 끝나게 한다.
    """
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(main())

    def _handle(sig: signal.Signals) -> None:
        logger.info("shutdown signal", extra={"signal": sig.name})
        on_signal()

    installed: list[signal.Signals] = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _handle, sig)
            installed.append(sig)

    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=None)
    except asyncio.CancelledError:
        on_signal()
        logger.warning("cancelled, draining", extra={"grace_seconds": grace_seconds})
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=grace_seconds)
        raise
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for sig in installed:
            with contextlib.suppress(NotImplementedError, ValueError):
                loop.remove_signal_handler(sig)
