"""인덱스 레지스트리.

현행은 레포지토리 `__init__`마다 `create_indexes()`를 호출해서 **요청마다**
인덱스 생성 커맨드가 나갔다(ISSUE-025). 여기서는 선언만 모아두고 부팅 시
한 번만 적용한다.

인덱스 **이름은 기존과 정확히 같아야 한다**(05 §1.3). 이름이 다르면 같은 키에
중복 인덱스가 생긴다.
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
