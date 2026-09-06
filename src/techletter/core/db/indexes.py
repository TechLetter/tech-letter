"""인덱스 레지스트리.

인덱스는 여기 선언만 모아두고 부팅 시 한 번만 적용한다.

인덱스 **이름을 함부로 바꾸지 않는다.** 이름이 바뀌면 기존 인덱스는 그대로
남은 채 같은 키에 새 인덱스가 하나 더 생긴다.

옵션(TTL·unique·partial)은 바꿔도 된다 — `ensure_indexes`가 실제 인덱스와
대조해서 맞춰 준다. Mongo는 같은 이름에 다른 옵션으로 생성하면 그냥 실패하기
때문에(`IndexOptionsConflict`), 대조 없이 만들기만 하면 옵션을 바꾼 순간
부팅이 깨진다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pymongo import IndexModel

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping

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


def _diff(spec: IndexSpec, existing: Mapping[str, Any]) -> str | None:
    """선언과 실제 인덱스의 차이를 돌려준다. 같으면 None."""
    if [(k, int(v)) for k, v in (existing.get("key") or {}).items()] != [
        (k, int(v)) for k, v in spec.keys
    ]:
        return "keys"
    if bool(existing.get("unique", False)) != spec.unique:
        return "unique"
    if (existing.get("partialFilterExpression") or None) != (spec.partial_filter or None):
        return "partial_filter"
    if existing.get("expireAfterSeconds") != spec.expire_after_seconds:
        return "ttl"
    return None


async def ensure_indexes(db: AsyncDatabase) -> dict[str, list[str]]:
    """등록된 인덱스를 실제로 만든다.

    이미 같은 이름·같은 옵션으로 있으면 no-op이다. 옵션이 달라졌으면 맞춰 준다.
    - TTL만 다르면 `collMod`로 값만 바꾼다(인덱스를 다시 만들지 않는다).
    - 그 밖의 옵션이 다르면 지우고 다시 만든다.
    """
    created: dict[str, list[str]] = {}
    for collection, specs in _REGISTRY.items():
        if not specs:
            continue
        cursor = await db[collection].list_indexes()
        existing = {idx["name"]: idx for idx in await cursor.to_list(length=None)}

        pending: list[IndexSpec] = []
        for spec in specs:
            current = existing.get(spec.name)
            if current is None:
                pending.append(spec)
                continue
            difference = _diff(spec, current)
            if difference is None:
                continue
            if difference == "ttl" and spec.expire_after_seconds is not None:
                await db.command(
                    {
                        "collMod": collection,
                        "index": {
                            "name": spec.name,
                            "expireAfterSeconds": spec.expire_after_seconds,
                        },
                    }
                )
                logger.info(
                    "index ttl updated",
                    extra={
                        "collection": collection,
                        "index": spec.name,
                        "expire_after_seconds": spec.expire_after_seconds,
                    },
                )
                continue
            # 옵션이 바뀌었으면 다시 만드는 수밖에 없다. 큰 컬렉션이면 재생성이
            # 오래 걸리므로 눈에 띄게 남긴다.
            logger.warning(
                "index options changed; recreating",
                extra={"collection": collection, "index": spec.name, "changed": difference},
            )
            await db[collection].drop_index(spec.name)
            pending.append(spec)

        if pending:
            names = await db[collection].create_indexes([s.to_model() for s in pending])
            created[collection] = names
        logger.info(
            "indexes ensured",
            # `created`는 LogRecord 예약 속성이라 extra에 쓰면 KeyError로 죽는다.
            extra={"collection": collection, "total": len(specs), "created_count": len(pending)},
        )
    return created
