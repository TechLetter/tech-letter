"""모델 추천 점수. 요약·챗봇이 모델을 고르는 순서와 모델 페이지의 추천순이 같이 쓴다.

    추천 점수 = 성능^a × 가용성^b × 속도^c

- 성능: Artificial Analysis Intelligence. 없으면 추정하지 않는다 — 추천 점수도 없다.
- 가용성: (24h 가용률 + 30일 가용률) / 2.
- 속도: 평균 응답이 5초 이하면 1, 느릴수록 √(5/초)로 깎인다.

순위는 상태(`classify_state`: 정상 → 불안정) 안에서 점수 있는 모델을 점수순으로, 그 뒤에
점수 없는 모델을 가용성 × 속도 순으로 둔다. 사용 불가 모델은 순위가 없다.

더하지 않고 곱한다. 더하면 점수가 높은 모델이 가용률 30%여도 위로 올라온다.
가중치(지수)는 설정값이다(`RECOMMEND_WEIGHT_*`, 기본 성능 1 · 가용성 2 · 속도 0.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from techletter.core.llm.model_scan import classify_state

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.settings import RouterSettings

__all__ = ["Candidate", "Recommendation", "candidates_from", "load_recommendations", "recommend"]

SPEED_TARGET_MS = 5_000


@dataclass(frozen=True, slots=True)
class Candidate:
    model_id: str
    state: str
    """healthy | degraded | down (`classify_state`)."""
    uptime_24h: float
    uptime_30d: float | None
    latency_ms: float | None
    intelligence: float | None


@dataclass(frozen=True, slots=True)
class Recommendation:
    score: float | None
    """성능 점수가 없거나 사용 불가인 모델은 없다."""
    rank: int | None
    """1부터. 지금 응답하지 않는 모델은 없다."""


def recommend(candidates: list[Candidate], settings: RouterSettings) -> dict[str, Recommendation]:
    def reliability(c: Candidate) -> float:
        uptime_30d = c.uptime_30d if c.uptime_30d is not None else c.uptime_24h
        availability = (c.uptime_24h + uptime_30d) / 200
        speed = min(1.0, (SPEED_TARGET_MS / c.latency_ms) ** 0.5) if c.latency_ms else 1.0
        return (
            availability**settings.recommend_weight_availability
            * speed**settings.recommend_weight_speed
        )

    def score(c: Candidate) -> float | None:
        if c.intelligence is None or c.state == "down":
            return None
        return (c.intelligence / 100) ** settings.recommend_weight_capability * reliability(c) * 100

    scores = {c.model_id: score(c) for c in candidates}
    tier = {"healthy": 0, "degraded": 1}
    ordered = sorted(
        (c for c in candidates if c.state in tier),
        key=lambda c: (
            tier[c.state],
            scores[c.model_id] is None,
            -(scores[c.model_id] or 0.0),
            -reliability(c),
            c.model_id,
        ),
    )
    ranks = {c.model_id: i + 1 for i, c in enumerate(ordered)}
    return {
        c.model_id: Recommendation(
            round(s, 1) if (s := scores[c.model_id]) is not None else None, ranks.get(c.model_id)
        )
        for c in candidates
    }


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
                state=classify_state(row),
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
