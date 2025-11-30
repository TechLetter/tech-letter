from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_CONFIG_FILE_NAME = "config.yaml"


@dataclass(slots=True)
class BlogSourceConfig:
    name: str
    url: str
    rss_url: str
    blog_type: str = "company"


@dataclass(slots=True)
class AggregateConfig:
    blog_fetch_batch_size: int
    blogs: list[BlogSourceConfig]


@dataclass(slots=True)
class AppConfig:
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


def load_aggregate_config() -> AggregateConfig:
    path = _find_config_path()
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    aggregate = data.get("aggregate") or {}
    raw_batch_size = aggregate.get("blog_fetch_batch_size", 10)
    try:
        batch_size = int(raw_batch_size)
    except (TypeError, ValueError) as exc:  # noqa: TRY003
        raise RuntimeError(
            f"invalid aggregate.blog_fetch_batch_size in {path}: {raw_batch_size!r}",
        ) from exc

    blogs_raw = aggregate.get("blogs") or []
    blogs: list[BlogSourceConfig] = []
    for item in blogs_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        rss_url = str(item.get("rss_url", "")).strip()
        blog_type = str(item.get("blog_type") or "company").strip() or "company"
        if not rss_url:
            continue
        blogs.append(
            BlogSourceConfig(
                name=name,
                url=url,
                rss_url=rss_url,
                blog_type=blog_type,
            ),
        )

    return AggregateConfig(blog_fetch_batch_size=batch_size, blogs=blogs)


def load_config() -> AppConfig:
    """content-service 설정을 로드하여 AppConfig 로 반환한다."""

    aggregate = load_aggregate_config()
    return AppConfig(aggregate=aggregate)
