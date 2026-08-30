"""인덱스 레지스트리.

인덱스는 여기 선언만 모아두고 부팅 시 한 번만 적용한다.

인덱스 **이름을 함부로 바꾸지 않는다.** 이름이 바뀌면 기존 인덱스는 그대로
남은 채 같은 키에 새 인덱스가 하나 더 생긴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pymongo import IndexModel

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

__all__ = ["IndexSpec", "clear_registry", "ensure_indexes", "register_indexes", "registered"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IndexSpec:
    name: str
    keys: list[tuple[str, int]]
    unique: bool = False
    expire_after_seconds: int | None = None
    partial_filter: dict[str, Any] | None = field(default=None)

    def to_model(self) -> IndexModel:
        kwargs: dict[str, Any] = {"name": self.name}
        if self.unique:
            kwargs["unique"] = True
        if self.expire_after_seconds is not None:
            kwargs["expireAfterSeconds"] = self.expire_after_seconds
        if self.partial_filter:
            kwargs["partialFilterExpression"] = self.partial_filter
        return IndexModel(self.keys, **kwargs)


_REGISTRY: dict[str, list[IndexSpec]] = {}


def register_indexes(collection: str, specs: list[IndexSpec]) -> None:
    """컬렉션의 인덱스를 등록한다. 같은 컬렉션을 여러 번 등록하면 합쳐진다."""
    existing = _REGISTRY.setdefault(collection, [])
    known = {s.name for s in existing}
    existing.extend(s for s in specs if s.name not in known)


def registered() -> dict[str, list[IndexSpec]]:
    return {k: list(v) for k, v in _REGISTRY.items()}


def clear_registry() -> None:
    """테스트 전용."""
    _REGISTRY.clear()


async def ensure_indexes(db: AsyncDatabase) -> dict[str, list[str]]:
    """등록된 인덱스를 실제로 생성한다. 이미 있으면 no-op이다."""
    created: dict[str, list[str]] = {}
    for collection, specs in _REGISTRY.items():
        if not specs:
            continue
        names = await db[collection].create_indexes([s.to_model() for s in specs])
        created[collection] = names
        logger.info("indexes ensured", extra={"collection": collection, "count": len(names)})
    return created
