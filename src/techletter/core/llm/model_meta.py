"""OpenRouter가 알려 주는 모델 정보(이름·컨텍스트·입력 종류·벤치마크·제공사).

헬스체크 스캔이 어차피 `/models`를 부르므로 그 응답을 버리지 않고 카탈로그
문서의 `meta`에 담는다. 가용률·지연은 우리 헬스체크 값만 쓴다 — OpenRouter의
엔드포인트 가용률은 우리 계정에서 403인 모델도 99%로 나와 믿을 수 없다.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pymongo import UpdateOne

from techletter.core.llm.model_events import CATALOG_COLLECTION

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

__all__ = ["endpoint_meta", "load_meta", "model_meta", "save_meta"]

_FREE_SUFFIX = re.compile(r"\s*\(free\)\s*$", re.IGNORECASE)
_BENCHMARKS = {
    "intelligence": "intelligence_index",
    "coding": "coding_index",
    "agentic": "agentic_index",
}


def model_meta(item: dict[str, Any]) -> dict[str, Any]:
    """`/models` 항목 하나에서 보여 줄 값만 고른다."""
    architecture = item.get("architecture") or {}
    params = item.get("supported_parameters") or []
    created = item.get("created")
    return {
        "name": _clean_name(item.get("name")),
        "description": item.get("description") or None,
        "context_length": item.get("context_length"),
        "created_at": datetime.fromtimestamp(created, UTC) if isinstance(created, int) else None,
        "input_modalities": list(architecture.get("input_modalities") or []),
        "tools": "tools" in params,
        "reasoning": "reasoning" in params,
        "hugging_face_id": item.get("hugging_face_id") or None,
        "benchmarks": _benchmarks(item.get("benchmarks")),
    }


def endpoint_meta(payload: dict[str, Any]) -> dict[str, Any]:
    """`/models/{id}/endpoints` 응답에서 제공사와 양자화만 고른다. 없으면 빈 dict."""
    data = payload.get("data") if isinstance(payload, dict) else None
    endpoints = data.get("endpoints") if isinstance(data, dict) else None
    if not endpoints or not isinstance(endpoints[0], dict):
        return {}
    first = endpoints[0]
    quantization = first.get("quantization")
    return {
        "provider": first.get("provider_name") or None,
        "quantization": None if quantization in (None, "", "unknown") else quantization,
    }


async def save_meta(db: AsyncDatabase, metas: dict[str, dict[str, Any]]) -> None:
    if metas:
        await db[CATALOG_COLLECTION].bulk_write(
            [
                UpdateOne({"_id": mid}, {"$set": {"meta": meta}}, upsert=True)
                for mid, meta in metas.items()
            ],
            ordered=False,
        )


async def load_meta(db: AsyncDatabase) -> dict[str, dict[str, Any]]:
    cursor = db[CATALOG_COLLECTION].find({"meta": {"$exists": True}}, projection={"meta": 1})
    return {str(doc["_id"]): doc["meta"] async for doc in cursor}


def _clean_name(name: Any) -> str | None:
    if not isinstance(name, str) or not name.strip():
        return None
    return " ".join(_FREE_SUFFIX.sub("", name).split())


def _benchmarks(raw: Any) -> dict[str, float] | None:
    scores = (raw or {}).get("artificial_analysis") if isinstance(raw, dict) else None
    if not isinstance(scores, dict):
        return None
    picked = {
        key: float(scores[field])
        for key, field in _BENCHMARKS.items()
        if isinstance(scores.get(field), int | float)
    }
    return picked or None
