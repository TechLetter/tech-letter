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
