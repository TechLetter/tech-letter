"""공개 모델 상태 DTO.

`json_failures`·`rate_limited`·실사용 성공률처럼 테크레터 내부 운영 사정을
드러내는 필드는 공개 API에 나가면 안 된다. 공개 스키마를 별도로 유지해 내부
운영 필드가 늘어나도 공개 API가 조용히 따라 늘어나지 않게 한다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from techletter.core.time import to_iso_z

__all__ = [
    "DailyUptimeOut",
    "ModelHealthOut",
    "ModelHealthSummaryOut",
]


class DailyUptimeOut(BaseModel):
    date: str
    uptime: float


class ModelHealthOut(BaseModel):
    model_id: str
    state: str
    """healthy | degraded | down — 지금 쓸 수 있는가(`classify_state`).
    down은 챗봇에서 고를 수 없다."""
    uptime_24h: float
    uptime_30d: float | None
    avg_latency_ms: float | None
    latest_status: str
    daily: list[DailyUptimeOut]
    """최근 30일, 오래된 날부터. 기록이 없는 날은 빠진다."""

    @classmethod
    def of(cls, row: dict[str, Any], daily: list[dict[str, Any]]) -> ModelHealthOut:
        from techletter.core.llm.model_scan import classify_state  # noqa: PLC0415

        uptime_24h = round(float(row.get("uptime_24h") or 0.0), 1)
        checks = sum(int(d.get("checks") or 0) for d in daily)
        successes = sum(int(d.get("successes") or 0) for d in daily)
        return cls(
            model_id=str(row.get("model_id") or ""),
            state=classify_state(row),
            uptime_24h=uptime_24h,
            uptime_30d=round(successes / checks * 100, 1) if checks else None,
            avg_latency_ms=row.get("avg_latency_24h"),
            latest_status=str(row.get("latest_status") or ""),
            daily=[
                DailyUptimeOut(date=d["date"], uptime=round(float(d["uptime"]), 1)) for d in daily
            ],
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
