"""공개 모델 상태 DTO.

어드민 스키마(`LlmModelStatOut` 등)와 겹치는 필드가 있어도 새로 정의한다 —
`json_failures`·`rate_limited`·실사용 성공률처럼 테크레터 내부 운영 사정을
드러내는 필드는 공개 API에 나가면 안 되고, 어드민 스키마가 나중에 필드를
늘려도 공개 API가 조용히 따라 늘어나면 안 된다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from techletter.core.time import to_iso_z

__all__ = [
    "ModelEventOut",
    "ModelHealthOut",
    "ModelHealthSummaryOut",
    "ModelHistoryPointOut",
]


class ModelHealthOut(BaseModel):
    model_id: str
    uptime_24h: float
    avg_latency_ms: float | None
    consecutive_failures: int
    latest_status: str

    @classmethod
    def of(cls, row: dict[str, Any]) -> ModelHealthOut:
        return cls(
            model_id=str(row.get("model_id") or ""),
            uptime_24h=round(float(row.get("uptime_24h") or 0.0), 1),
            avg_latency_ms=row.get("avg_latency_24h"),
            consecutive_failures=int(row.get("consecutive_failures") or 0),
            latest_status=str(row.get("latest_status") or ""),
        )


class ModelHealthSummaryOut(BaseModel):
    total_models: int
    healthy_count: int
    degraded_count: int
    down_count: int
    last_checked_at: str | None

    @classmethod
    def of(cls, summary: dict[str, Any], last_checked_at: Any) -> ModelHealthSummaryOut:
        return cls(
            total_models=summary["total_models"],
            healthy_count=summary["healthy_count"],
            degraded_count=summary["degraded_count"],
            down_count=summary["down_count"],
            last_checked_at=to_iso_z(last_checked_at),
        )


class ModelHistoryPointOut(BaseModel):
    date: str
    checks: int
    successes: int
    uptime: float
    rate_limited: int
    avg_latency_ms: float | None

    @classmethod
    def of(cls, row: dict[str, Any]) -> ModelHistoryPointOut:
        return cls(
            date=row["date"],
            checks=row["checks"],
            successes=row["successes"],
            uptime=round(row["uptime"], 1),
            rate_limited=row["rate_limited"],
            avg_latency_ms=row.get("avg_latency_ms"),
        )


class ModelEventOut(BaseModel):
    model_id: str
    type: str
    detected_at: str | None
    reason: str | None

    @classmethod
    def of(cls, row: dict[str, Any]) -> ModelEventOut:
        return cls(
            model_id=row["model_id"],
            type=row["type"],
            detected_at=to_iso_z(row.get("detected_at")),
            reason=row.get("reason"),
        )
