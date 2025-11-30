from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


DEFAULT_CONFIG_FILE_NAME = "config.yaml"


class BlogSourceConfig(BaseModel):
    name: str
    url: str
    rss_url: str
    blog_type: str = Field(default="company", alias="blog_type")


class AggregateConfig(BaseModel):
    blog_fetch_batch_size: int = Field(default=10)
    blogs: list[BlogSourceConfig] = Field(default_factory=list)


class AppConfig(BaseModel):
    """content-service 전체 설정 루트.

    - 현재는 aggregate 섹션만 사용하지만, 추후 api/logging 등의 서브 설정을 추가할 수 있다.
    """

    aggregate: AggregateConfig


def _find_config_path() -> Path:
    """현재 작업 디렉토리 기준으로 상위로 올라가며 config.yaml 을 찾는다.

    Go `config.GetBasePath` 와 동일한 의도를 유지하되, Python 쪽에서는
    content-service 가 레포지토리 루트에서 실행된다는 전제를 사용한다.
    """

    current = Path.cwd()
    for directory in (current, *current.parents):
        candidate = directory / DEFAULT_CONFIG_FILE_NAME
        if candidate.is_file():
            return candidate

    raise RuntimeError(
        f"{DEFAULT_CONFIG_FILE_NAME} not found. Place config.yaml in project root.",
    )


def load_config() -> AppConfig:
    """content-service 설정을 로드하여 AppConfig 로 반환한다."""

    path = _find_config_path()
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    content_service = data.get("content_service")
    if not isinstance(content_service, dict):
        raise RuntimeError(
            f"config.yaml must contain 'content_service' mapping; got: {type(content_service).__name__}",
        )

    try:
        return AppConfig.model_validate(content_service)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"failed to validate content_service config at {path}: {exc}",
        ) from exc
