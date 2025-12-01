from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Go eventbus.RetryDelays와 동일한 재시도 횟수/순서를 유지한다.
RetryDelays: list[float] = [
    60.0,  # 1 * time.Minute,
    300.0,  # 5 * time.Minute,
    600.0,  # 10 * time.Minute,
    1800.0,  # 30 * time.Minute,
    3600.0,  # 1 * time.Hour,
]


class MaxRetryExceededError(Exception):
    """최대 재시도 횟수를 초과한 경우 사용되는 예외."""


@dataclass(slots=True)
class Event:
    """Kafka 메시지의 메타데이터와 페이로드를 표현하는 이벤트.

    payload는 직렬화 직전/직후 형태(예: dict 또는 bytes)를 저장하는 용도로 사용하고,
    실제 Kafka I/O 레이어에서 JSON 인코딩/디코딩을 담당한다.
    """

    id: str
    payload: Any
    retry: int = 0
    max_retry: int = 0
    last_error: str | None = None

    def __post_init__(self) -> None:
        if self.max_retry <= 0 or self.max_retry > len(RetryDelays):
            self.max_retry = len(RetryDelays)


@dataclass(frozen=True, slots=True)
class Topic:
    base: str

    def dlq(self) -> str:
        return f"{self.base}.dlq"

    def get_retry_topics(self) -> list[str]:
        return [
            f"{self.base}.retry.{index}" for index in range(1, len(RetryDelays) + 1)
        ]

    def get_retry_topic(self, retry_count: int) -> str:
        if retry_count <= 0 or retry_count > len(RetryDelays):
            raise MaxRetryExceededError()
        return f"{self.base}.retry.{retry_count}"
