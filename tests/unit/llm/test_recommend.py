"""추천 순위 = 상태 안에서 성능 × 가용성 × 속도. 성능 점수가 없으면 추정하지 않는다."""

from __future__ import annotations

from techletter.core.llm.recommend import Candidate, recommend
from techletter.settings import RouterSettings


def model(model_id: str, intelligence: float | None, uptime: float = 100.0, **kw) -> Candidate:
    return Candidate(
        model_id=model_id,
        state=kw.get("state", "healthy" if uptime >= 90 else "degraded"),
        uptime_24h=uptime,
        uptime_30d=kw.get("uptime_30d", uptime),
        latency_ms=kw.get("latency_ms", 1000),
        intelligence=intelligence,
    )


def ranks(candidates: list[Candidate], **settings) -> list[str]:
    recs = recommend(candidates, RouterSettings(**settings))
    ranked = [mid for mid, r in recs.items() if r.rank is not None]
    return sorted(ranked, key=lambda mid: recs[mid].rank or 0)


def test_a_healthy_model_comes_before_an_unstable_one_whatever_the_score() -> None:
    assert ranks([model("glm", 33.7, uptime=60), model("ultra", 22.9, uptime=97)]) == [
        "ultra",
        "glm",
    ]


def test_an_unscored_model_has_no_score_and_follows_the_scored_ones() -> None:
    """성능을 추정하지 않는다. 점수 없는 모델은 같은 상태의 점수 있는 모델 뒤, 가용성순."""
    recs = recommend(
        [model("unknown", None), model("known", 9.9, uptime=92), model("flaky", None, uptime=91)],
        RouterSettings(),
    )

    assert recs["unknown"].score is None
    assert [m for m, _ in sorted(recs.items(), key=lambda x: x[1].rank or 99)] == [
        "known",
        "unknown",
        "flaky",
    ]


def test_a_slow_model_is_pushed_down() -> None:
    """응답 26초면 속도 요소가 크게 깎는다(Lightning 12.9점 < Super 12.8점)."""
    assert ranks([model("lightning", 12.9, latency_ms=26_000), model("super", 12.8)]) == [
        "super",
        "lightning",
    ]


def test_an_unusable_model_gets_no_rank() -> None:
    recs = recommend([model("down", 33.7, uptime=20, state="down")], RouterSettings())

    assert recs["down"].rank is None


def test_weights_come_from_settings() -> None:
    candidates = [model("smart", 30.0, uptime=92), model("steady", 20.0, uptime=100)]

    assert ranks(candidates, RECOMMEND_WEIGHT_AVAILABILITY=40.0) == ["steady", "smart"]
    assert ranks(candidates) == ["smart", "steady"]
