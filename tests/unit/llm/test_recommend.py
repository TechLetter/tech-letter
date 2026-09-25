"""추천 점수 = 성능 × 가용성 × 속도."""

from __future__ import annotations

from techletter.core.llm.recommend import Candidate, recommend
from techletter.settings import RouterSettings


def model(model_id: str, intelligence: float | None, uptime: float = 100.0, **kw) -> Candidate:
    return Candidate(
        model_id=model_id,
        available=kw.get("available", True),
        uptime_24h=uptime,
        uptime_30d=kw.get("uptime_30d", uptime),
        latency_ms=kw.get("latency_ms", 1000),
        intelligence=intelligence,
    )


def ranks(candidates: list[Candidate], **settings) -> list[str]:
    recs = recommend(candidates, RouterSettings(**settings))
    ranked = [mid for mid, r in recs.items() if r.rank is not None]
    return sorted(ranked, key=lambda mid: recs[mid].rank or 0)


def test_a_high_score_does_not_make_up_for_poor_availability() -> None:
    """GLM 5.2(33.7점, 가용률 30%)가 22.9점·97%인 모델을 이기면 안 된다."""
    assert ranks([model("glm", 33.7, uptime=30), model("ultra", 22.9, uptime=97)]) == [
        "ultra",
        "glm",
    ]


def test_an_unscored_model_counts_as_the_lowest_known_score() -> None:
    recs = recommend([model("known", 9.9), model("unknown", None)], RouterSettings())

    assert recs["unknown"].score == recs["known"].score


def test_a_slow_model_is_pushed_down() -> None:
    """응답 26초면 속도 요소가 크게 깎는다(Lightning 12.9점 < Super 12.8점)."""
    assert ranks([model("lightning", 12.9, latency_ms=26_000), model("super", 12.8)]) == [
        "super",
        "lightning",
    ]


def test_a_model_that_does_not_answer_now_gets_no_rank() -> None:
    recs = recommend([model("down", 33.7, available=False)], RouterSettings())

    assert (recs["down"].score, recs["down"].rank) == (0.0, None)


def test_weights_come_from_settings() -> None:
    candidates = [model("smart", 30.0, uptime=60), model("steady", 20.0, uptime=100)]

    assert ranks(candidates) == ["steady", "smart"]
    assert ranks(candidates, RECOMMEND_WEIGHT_CAPABILITY=3.0) == ["smart", "steady"]
