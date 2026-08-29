"""계획 파싱과 정규화."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from techletter.chat.agent.planner import KST, QueryPlanner, parse_plan
from techletter.chat.agent.policies import (
    DEFAULT_POST_LIMIT,
    MAX_POST_LIMIT,
    normalize_plan,
    should_return_no_result,
)
from techletter.chat.agent.state import ChatPlan, PostConstraints, ToolResult


def test_a_full_payload_is_parsed() -> None:
    plan = parse_plan(
        {
            "task": "list_posts",
            "constraints": {
                "published_from": "2025-03-01T00:00:00Z",
                "published_to": "2025-03-31T23:59:59+09:00",
                "blog_name": " 카카오 ",
                "categories": ["AI", " ai ", ""],
                "tags": ["Kafka"],
                "limit": 5,
            },
            "strict_scope": True,
            "needs_content": False,
            "reason": "목록 요청",
        }
    )

    assert plan.task == "list_posts"
    assert plan.constraints.published_from == datetime(2025, 3, 1, tzinfo=UTC)
    assert plan.constraints.blog_name == "카카오"
    assert plan.constraints.categories == ["AI"]  # 공백·중복 제거
    assert plan.constraints.limit == 5
    assert plan.reason == "목록 요청"


def test_an_unknown_task_falls_back_to_general_rag() -> None:
    assert parse_plan({"task": "delete_everything"}).task == "general_rag"


def test_a_missing_constraints_object_is_tolerated() -> None:
    plan = parse_plan({"task": "general_rag", "constraints": "nope"})

    assert plan.constraints.limit == DEFAULT_POST_LIMIT


def test_an_unparsable_date_is_dropped_rather_than_raising() -> None:
    """모델이 "지난달"을 그대로 넣기도 한다. 제약만 버린다."""
    plan = parse_plan({"task": "list_posts", "constraints": {"published_from": "지난달"}})

    assert plan.constraints.published_from is None


def test_a_naive_datetime_is_treated_as_utc() -> None:
    plan = parse_plan({"task": "list_posts", "constraints": {"published_from": "2025-03-01"}})

    assert plan.constraints.published_from == datetime(2025, 3, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 0은 "안 정했다"는 뜻이라 기본값을 쓴다.
        (0, DEFAULT_POST_LIMIT),
        ("abc", DEFAULT_POST_LIMIT),
        (-5, 1),
        (999, MAX_POST_LIMIT),
        (7, 7),
    ],
)
def test_limits_are_clamped(raw: object, expected: int) -> None:
    plan = parse_plan({"task": "list_posts", "constraints": {"limit": raw}})

    assert plan.constraints.limit == expected


def test_any_scope_constraint_turns_on_strict_scope() -> None:
    """범위를 못 박은 질문에 엉뚱한 최신 글로 답하지 않기 위한 장치다."""
    plan = normalize_plan(ChatPlan(task="general_rag", constraints=PostConstraints(tags=["Go"])))

    assert plan.strict_scope is True


def test_no_constraints_means_no_strict_scope() -> None:
    assert normalize_plan(ChatPlan(task="general_rag")).strict_scope is False


@pytest.mark.parametrize("task", ["summarize_posts", "answer_from_posts"])
def test_content_tasks_imply_needs_content(task: str) -> None:
    assert normalize_plan(ChatPlan(task=task)).needs_content is True  # type: ignore[arg-type]


def test_strict_scope_with_no_results_short_circuits() -> None:
    plan = normalize_plan(ChatPlan(task="list_posts", constraints=PostConstraints(tags=["Go"])))

    assert should_return_no_result(plan, ToolResult(status="no_result")) is True
    assert should_return_no_result(plan, ToolResult(status="ok")) is False


def test_loose_scope_with_no_results_keeps_going() -> None:
    plan = normalize_plan(ChatPlan(task="general_rag"))

    assert should_return_no_result(plan, ToolResult(status="no_result")) is False


class FakeLlm:
    def __init__(self, payload: dict | Exception) -> None:
        self.payload = payload
        self.calls = 0

    async def complete_json(self, purpose, system, user, **kwargs):
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload, "test-model"


async def test_planner_normalizes_the_model_output() -> None:
    llm = FakeLlm({"task": "list_posts", "constraints": {"tags": ["Go"], "limit": 100}})

    plan = await QueryPlanner(llm).plan("go 글 보여줘", {})  # type: ignore[arg-type]

    assert plan.task == "list_posts"
    assert plan.constraints.limit == MAX_POST_LIMIT
    assert plan.strict_scope is True


async def test_a_failed_planner_falls_back_instead_of_raising() -> None:
    """계획이 실패해도 대화는 이어져야 한다. 벡터 검색은 제약 없이 동작한다."""
    llm = FakeLlm(RuntimeError("all models failed"))

    plan = await QueryPlanner(llm).plan("아무거나", {})  # type: ignore[arg-type]

    assert plan.task == "general_rag"
    assert plan.reason == "planner_failed"


async def test_the_planner_prompt_carries_the_current_time() -> None:
    """ "지난달"을 날짜로 바꾸려면 지금이 언제인지 알아야 한다."""
    captured: dict[str, str] = {}

    class Capturing(FakeLlm):
        async def complete_json(self, purpose, system, user, **kwargs):
            captured["system"] = system
            captured["purpose"] = purpose
            return {"task": "general_rag"}, "m"

    await QueryPlanner(Capturing({})).plan("질문", {})  # type: ignore[arg-type]

    assert "Asia/Seoul" in captured["system"]
    assert str(datetime.now(KST).year) in captured["system"]
    assert captured["purpose"] == "planner"
