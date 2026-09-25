"""모델 추천 점수. 요약·챗봇이 모델을 고르는 순서와 모델 페이지의 추천순이 같이 쓴다.

    추천 점수 = 성능^a × 가용성^b × 속도^c

- 성능: Artificial Analysis Intelligence. 없으면 후보 중 가장 낮은 점수로 본다 — 모르는
  모델이 검증된 점수를 이기지 못하게.
- 가용성: (24h 가용률 + 30일 가용률) / 2. 지금 응답하지 않으면 0 — 후보에서 빠진다.
- 속도: 평균 응답이 5초 이하면 1, 느릴수록 √(5/초)로 깎인다.

더하지 않고 곱한다. 더하면 점수가 높은 모델이 가용률 30%여도 위로 올라온다.
가중치(지수)는 설정값이다(`RECOMMEND_WEIGHT_*`, 기본 성능 1 · 가용성 2 · 속도 0.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.settings import RouterSettings

__all__ = ["Candidate", "Recommendation", "candidates_from", "load_recommendations", "recommend"]

SPEED_TARGET_MS = 5_000


@dataclass(frozen=True, slots=True)
class Candidate:
    model_id: str
    available: bool
    """지금 응답하는가(마지막 체크 성공)."""
    uptime_24h: float
    uptime_30d: float | None
    latency_ms: float | None
    intelligence: float | None


@dataclass(frozen=True, slots=True)
class Recommendation:
    score: float
    rank: int | None
    """1부터. 지금 응답하지 않는 모델은 없다."""


def recommend(candidates: list[Candidate], settings: RouterSettings) -> dict[str, Recommendation]:
    known = [c.intelligence for c in candidates if c.intelligence is not None]
    floor = min(known) if known else 1.0

    def score(c: Candidate) -> float:
        if not c.available:
            return 0.0
        capability = (c.intelligence if c.intelligence is not None else floor) / 100
        uptime_30d = c.uptime_30d if c.uptime_30d is not None else c.uptime_24h
        availability = (c.uptime_24h + uptime_30d) / 200
        speed = min(1.0, (SPEED_TARGET_MS / c.latency_ms) ** 0.5) if c.latency_ms else 1.0
        return (
            capability**settings.recommend_weight_capability
            * availability**settings.recommend_weight_availability
            * speed**settings.recommend_weight_speed
            * 100
        )

    scores = {c.model_id: score(c) for c in candidates}
    ordered = sorted(
        (c for c in candidates if c.available and scores[c.model_id] > 0),
        key=lambda c: (-scores[c.model_id], c.model_id),
    )
    ranks = {c.model_id: i + 1 for i, c in enumerate(ordered)}
    return {mid: Recommendation(round(s, 1), ranks.get(mid)) for mid, s in scores.items()}


def candidates_from(
    health: list[dict[str, Any]],
    daily: dict[str, list[dict[str, Any]]],
    meta: dict[str, dict[str, Any]],
) -> list[Candidate]:
    """헬스체크 집계(`compute_health`)·일별 기록·모델 정보를 추천 입력으로 모은다."""
    out: list[Candidate] = []
    for row in health:
        model_id = str(row.get("model_id") or "")
        days = daily.get(model_id, [])
        checks = sum(int(d.get("checks") or 0) for d in days)
        successes = sum(int(d.get("successes") or 0) for d in days)
        out.append(
            Candidate(
                model_id=model_id,
                available=str(row.get("latest_status") or "").upper() == "OK",
                uptime_24h=float(row.get("uptime_24h") or 0.0),
                uptime_30d=successes / checks * 100 if checks else None,
                latency_ms=row.get("avg_latency_24h"),
                intelligence=((meta.get(model_id) or {}).get("benchmarks") or {}).get(
                    "intelligence"
                ),
            )
        )
    return out


async def load_recommendations(
    db: AsyncDatabase, settings: RouterSettings, health: list[dict[str, Any]] | None = None
) -> dict[str, Recommendation]:
    from techletter.core.llm.model_history import history  # noqa: PLC0415
    from techletter.core.llm.model_meta import load_meta  # noqa: PLC0415
    from techletter.core.llm.model_scan import compute_health  # noqa: PLC0415

    rows = health if health is not None else await compute_health(db)
    daily: dict[str, list[dict[str, Any]]] = {}
    for row in await history(db, days=30):
        daily.setdefault(row["model_id"], []).append(row)
    return recommend(candidates_from(rows, daily, await load_meta(db)), settings)
