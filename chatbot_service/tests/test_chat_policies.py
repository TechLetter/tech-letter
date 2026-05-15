from __future__ import annotations

from datetime import datetime, timezone

from chatbot_service.app.domain.chat.policies import normalize_plan
from chatbot_service.app.domain.chat.schemas import ChatPlan, PostConstraints


def test_normalize_plan_forces_strict_scope_for_date_constraints() -> None:
    plan = ChatPlan(
        task="list_posts",
        constraints=PostConstraints(
            published_from=datetime(2026, 5, 14, tzinfo=timezone.utc),
            limit=100,
        ),
        strict_scope=False,
    )

    normalized = normalize_plan(plan)

    assert normalized.strict_scope
    assert normalized.constraints.limit == 20


def test_normalize_plan_marks_content_tasks_as_needing_content() -> None:
    plan = ChatPlan(task="summarize_posts", needs_content=False)

    normalized = normalize_plan(plan)

    assert normalized.needs_content
