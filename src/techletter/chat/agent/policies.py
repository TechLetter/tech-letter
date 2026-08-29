"""계획 정규화 규칙.

LLM이 만든 계획을 그대로 믿지 않는다. 한도를 강제하고, 범위 제약이 있으면
`strict_scope`를 켠다 — 사용자가 "지난달 카카오 글"을 물었는데 최신 글로
대체 답변하는 일을 막는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.chat.agent.state import ChatPlan, PostConstraints
from techletter.core.time import ensure_utc

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from techletter.chat.agent.state import ToolResult

__all__ = [
    "CONTENT_TASKS",
    "DEFAULT_POST_LIMIT",
    "MAX_POST_LIMIT",
    "normalize_constraints",
    "normalize_plan",
    "should_return_no_result",
]

DEFAULT_POST_LIMIT = 10
MAX_POST_LIMIT = 20
CONTENT_TASKS = frozenset({"summarize_posts", "answer_from_posts"})


def _dedupe(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


def _utc(value: datetime | None) -> datetime | None:
    return ensure_utc(value) if value is not None else None


def normalize_constraints(constraints: PostConstraints) -> PostConstraints:
    return PostConstraints(
        published_from=_utc(constraints.published_from),
        published_to=_utc(constraints.published_to),
        blog_name=(constraints.blog_name or "").strip() or None,
        categories=_dedupe(constraints.categories),
        tags=_dedupe(constraints.tags),
        limit=max(1, min(constraints.limit or DEFAULT_POST_LIMIT, MAX_POST_LIMIT)),
    )


def normalize_plan(plan: ChatPlan) -> ChatPlan:
    constraints = normalize_constraints(plan.constraints)
    return ChatPlan(
        task=plan.task,
        constraints=constraints,
        strict_scope=plan.strict_scope or constraints.has_scope(),
        needs_content=plan.needs_content or plan.task in CONTENT_TASKS,
        reason=plan.reason,
    )


def should_return_no_result(plan: ChatPlan, result: ToolResult) -> bool:
    """범위를 못 박은 질문에서 결과가 없으면 그대로 "없음"이라고 답한다."""
    return plan.strict_scope and result.status == "no_result"
