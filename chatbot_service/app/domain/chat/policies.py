from __future__ import annotations

from dataclasses import replace
from datetime import timezone

from .schemas import ChatPlan, PostConstraints, ToolResult


MAX_POST_LIMIT = 20
DEFAULT_POST_LIMIT = 10


def normalize_plan(plan: ChatPlan) -> ChatPlan:
    constraints = normalize_constraints(plan.constraints)
    strict_scope = plan.strict_scope or _requires_strict_scope(constraints)
    needs_content = plan.needs_content or plan.task in {
        "summarize_posts",
        "answer_from_posts",
    }
    return replace(
        plan,
        constraints=constraints,
        strict_scope=strict_scope,
        needs_content=needs_content,
    )


def normalize_constraints(constraints: PostConstraints) -> PostConstraints:
    limit = constraints.limit or DEFAULT_POST_LIMIT
    limit = max(1, min(limit, MAX_POST_LIMIT))
    return PostConstraints(
        published_from=_normalize_datetime(constraints.published_from),
        published_to=_normalize_datetime(constraints.published_to),
        blog_name=(constraints.blog_name or "").strip() or None,
        categories=_clean_values(constraints.categories),
        tags=_clean_values(constraints.tags),
        limit=limit,
    )


def should_return_no_result(plan: ChatPlan, result: ToolResult) -> bool:
    return plan.strict_scope and result.status == "no_result"


def _requires_strict_scope(constraints: PostConstraints) -> bool:
    return constraints.has_scope()


def _normalize_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _clean_values(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return cleaned
