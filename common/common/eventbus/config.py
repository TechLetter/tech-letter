from __future__ import annotations

import os


def get_brokers() -> str:
    value = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if not value:
        raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS environment variable is required")
    return value


def get_group_id() -> str:
    value = os.getenv("KAFKA_GROUP_ID")
    if not value:
        raise RuntimeError("KAFKA_GROUP_ID environment variable is required")
    return value


def get_message_max_bytes() -> int | None:
    """Kafka producer에서 사용할 최대 메시지 크기(message.max.bytes)를 반환한다.

    - 환경 변수 KAFKA_MESSAGE_MAX_BYTES가 비어있으면 None 을 반환한다.
    - 0 이하 값은 라이브러리 기본값을 사용하겠다는 의미로 간주하고 None 을 반환한다.
    - 정수가 아닌 값이 들어오면 명시적인 에러를 발생시켜 조기에 설정 문제를 발견한다.
    """

    raw_value = os.getenv("KAFKA_MESSAGE_MAX_BYTES", "").strip()
    if not raw_value:
        return None

    try:
        value = int(raw_value)
    except ValueError as exc:  # noqa: TRY003
        raise RuntimeError(
            "KAFKA_MESSAGE_MAX_BYTES must be an integer value, got: " f"{raw_value!r}"
        ) from exc

    if value <= 0:
        return None

    return value
