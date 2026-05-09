from __future__ import annotations

import os

from pydantic import BaseModel, Field


BLOG_FETCH_BATCH_SIZE_ENV = "CONTENT_BLOG_FETCH_BATCH_SIZE"


class AggregateConfig(BaseModel):
    blog_fetch_batch_size: int = Field(default=10)


class AppConfig(BaseModel):
    """content-service 전체 설정 루트.

    - 수집 대상 블로그는 MongoDB blogs 컬렉션에서 관리한다.
    - 런타임 설정은 환경변수에서 읽는다.
    """

    aggregate: AggregateConfig


def _get_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer; got {raw_value!r}") from exc

    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer; got {raw_value!r}")

    return value


def load_config() -> AppConfig:
    """content-service 설정을 환경변수에서 로드한다."""

    return AppConfig(
        aggregate=AggregateConfig(
            blog_fetch_batch_size=_get_positive_int_env(
                BLOG_FETCH_BATCH_SIZE_ENV,
                10,
            ),
        ),
    )
